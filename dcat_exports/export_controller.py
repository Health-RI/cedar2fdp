from abc import ABCMeta
from typing import Dict, List

import pandas as pd

from cedar.client import CedarClient
from core.logger import get_logger

logger = get_logger()


class CedarFieldError(Exception):
    pass


class CedarConfig(ABCMeta):
    admin_templ_id: str
    catalog_templ_id: str
    content_templ_id: str
    dataset_templ_id: str
    distribution_templ_id: str


class ExportController:
    def __init__(self, client: CedarClient, bc_config: CedarConfig):
        self.client = client
        self.catalog_ids = self.client.search_instances(bc_config.catalog_templ_id)
        self.content_ids = self.client.search_instances(bc_config.content_templ_id)
        self.dataset_ids = self.client.search_instances(bc_config.dataset_templ_id)
        self.admin_ids = self.client.search_instances(bc_config.admin_templ_id)
        self.distribution_ids = self.client.search_instances(
            bc_config.distribution_templ_id
        )
        self.overall_mapping = None
        self.removed_records = None

    def get_catalogs_data(self):
        catalog_templ_instances = []
        for instance_id in self.catalog_ids:
            catalog_instance = self.client.get_template_instance(instance_id).json()
            # get and validate description
            description = catalog_instance["catalogDescription"].get("@value")
            if description is None or description == "":
                logger.error(f"Empty catalog description: {instance_id}, skipping")
                continue
            # get and validate content id
            project_id = self._get_and_validate_content_reference(catalog_instance)
            # get and validate dataset template instances' ids
            datasets = self._get_and_validate_datasets(catalog_instance, instance_id)

            instance_dict = {
                "catalog_instance_id": instance_id,
                "content_instance_id": project_id,
                "description": description,
                "publisher": catalog_instance["publisher"].get("@id"),
                "dataset_id": datasets,
            }
            catalog_templ_instances.append(instance_dict)

        catalog_temp_instances_df = pd.DataFrame(data=catalog_templ_instances).explode(
            "dataset_id"
        )
        return catalog_temp_instances_df

    def _get_and_validate_content_reference(self, catalog_instance: Dict) -> str:
        catalog_log = f"Catalog template {catalog_instance['@id']}"
        # typo in Cedar, adding "ProjectContentInstanceID" in case it will be corrected
        possible_keys = [
            "ProjectContentIntanceID",
            "projectIdentifier",
            "ProjectContentInstanceID",
        ]
        project_id = None
        for key in possible_keys:
            project_id = catalog_instance.get(key)
            if project_id is not None and isinstance(project_id, List):
                break
        if project_id is None:
            logger.warning(
                f"{catalog_log} does not contain any of project keys: {', '.join(possible_keys)}"
            )
        elif isinstance(project_id, dict):
            project_id = project_id.get("@id")
        else:
            if len(project_id) > 1:
                logger.error(
                    f"{catalog_log} is referring to several projects, please check"
                )
                raise CedarFieldError
            project_id = project_id[0].get("@id")
        if project_id is not None and project_id not in self.content_ids:
            logger.error(
                f"{catalog_log} is referring to a not existing Content template: {project_id}"
            )
        return project_id

    def _get_and_validate_datasets(
        self, catalog_instance: Dict, instance_id: str
    ) -> List:
        datasets = [ds.get("@id") for ds in catalog_instance["datasetIdentifier"]]
        datasets_validated = datasets.copy()
        for data_set in datasets:
            if data_set is not None and not data_set.startswith(self.client.base_url):
                logger.warning(
                    f"Unexpected dataset link: {data_set}, Catalog ID {instance_id}; skipping"
                )
                datasets_validated.remove(data_set)
            elif data_set not in self.dataset_ids:
                logger.warning(
                    f"Dataset {data_set} is not an instance of Dataset Template"
                )
        return datasets_validated

    def merge_datasets_distributions_ids(self):
        linked_dist = []
        dist_validation_list = []
        new_line = "\n"
        dataset_ids = self.overall_mapping["dataset_id"].dropna().unique()
        for dataset_id in dataset_ids:
            dataset_json = self.client.get_template_instance(dataset_id).json()
            field_name = "DistributionMetadataInstanceID"
            try:
                distributions = dataset_json[field_name]
            except KeyError:
                field_name = "datasetDistributionIdentifier"
                distributions = dataset_json.get(field_name)
                if distributions is None:
                    logger.warning(
                        f"Dataset {dataset_id} does not contain any of distribution keys: "
                        f"'DistributionMetadataInstanceID', 'datasetDistributionIdentifier'"
                    )
                    continue
            for distr in distributions:
                distr_id = distr["@id"]
                linked_dist.append(
                    {"dataset_id": dataset_id, "distribution_id": distr_id}
                )
                dist_validation_list.append(distr_id)

        missing_datasets = [
            dset for dset in self.dataset_ids if dset not in dataset_ids
        ]
        if missing_datasets:
            logger.warning(
                f"Following datasets are not referenced from a catalog: {f',{new_line}'.join(missing_datasets)}"
            )

        missed = [i for i in self.distribution_ids if i not in dist_validation_list]
        if missed:
            logger.warning(
                f"Following distributions are not referenced from a catalog: {f',{new_line}'.join(missed)}"
            )
        data_frame = pd.DataFrame(linked_dist)
        self.overall_mapping = pd.merge(
            self.overall_mapping, data_frame, how="outer", on="dataset_id"
        )

    def merge_content_data(self):
        """For each instance of Content Template searches for focus area"""
        content_data_dicts = []
        for content_instance_id in self.content_ids:
            content_templ_json = self.client.get_template_instance(
                content_instance_id
            ).json()
            content_dict = {"content_instance_id": content_instance_id, "keyword": []}
            scope = content_templ_json["Scope"]
            focus_area = scope["Focus Area"]["Focus Area"]

            content_dict["focus_area_id"] = focus_area.get("@id")
            if content_dict["focus_area_id"] is None:
                logger.warning(
                    f"No Focus Area specified for Content Template {content_instance_id}"
                )
            fa_label = focus_area.get("rdfs:label")
            content_dict["focus_area"] = fa_label
            if fa_label == "other":
                content_dict["keyword"].append(
                    scope["Focus Area"]["Other Focus Area"].get("@value")
                )
            keywords = []
            themes = []
            self.collect_content_scope_data(scope, keywords, themes)
            content_dict["keyword"] += keywords
            content_dict["theme"] = themes
            content_dict["admin_instance_id"] = content_templ_json["Other"][
                "Project Admin Instance ID"
            ]["Project Admin Instance ID"].get("@value")
            content_data_dicts.append(content_dict)
        contents_df = pd.DataFrame(data=content_data_dicts)
        td = pd.merge(
            self.overall_mapping, contents_df, how="outer", on="content_instance_id"
        )
        admin_df = pd.DataFrame(data={"admin_instance_id": self.admin_ids})
        admin_df["admin_graph_id"] = admin_df.index.map(
            lambda x: f"http://example.com/dataset/{str(x)}"
        )
        td = pd.merge(admin_df, td, how="outer", on="admin_instance_id")
        # todo: maybe admin validation?
        return td

    def collect_content_scope_data(self, scope, keywords, themes):
        if isinstance(scope, List):
            for item in scope:
                self.collect_content_scope_data(item, keywords, themes)
        elif isinstance(scope, Dict):
            for key, value in scope.items():
                if key not in ["@context", "Focus Area", "@id", "@value", "rdfs:label"]:
                    nested_object = scope[key]
                    self.collect_content_scope_data(nested_object, keywords, themes)
                elif (
                    key == "@id"
                    and value
                    and not value.startswith(
                        f"{self.client.base_url}/template-element-instances"
                    )
                ):
                    themes.append(value)
                elif key in ["@value", "rdfs:label"] and value:
                    keywords.append(value)
        return keywords, themes
