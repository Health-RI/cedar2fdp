import re
from abc import ABCMeta
from typing import Dict, List, Union

import numpy as np
import pandas as pd
import w3lib.url

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
            project_id = self._get_and_validate_admin_reference(catalog_instance)
            # get and validate dataset template instances' ids
            datasets = self._get_and_validate_datasets(catalog_instance, instance_id)

            instance_dict = {
                "catalog_instance_id": instance_id,
                "admin_instance_id": project_id,
                "description": description,
                "publisher": catalog_instance["publisher"].get("@id"),
                "dataset_id": datasets,
            }
            catalog_templ_instances.append(instance_dict)

        catalog_temp_instances_df = pd.DataFrame(data=catalog_templ_instances).explode(
            "dataset_id"
        )
        catalog_temp_instances_df = self._normalize_template_link_columns(
            catalog_temp_instances_df, "admin_instance_id"
        )
        catalog_temp_instances_df = self._normalize_template_link_columns(
            catalog_temp_instances_df, "dataset_id"
        )
        return catalog_temp_instances_df

    def _get_and_validate_admin_reference(
        self, catalog_instance: Dict
    ) -> Union[str, None]:
        """
        Gets Admin Template Instance reference from a Catalog Template Instance
        Checks if the URL provided is a link to an Admin Instance, retrieves Admin Instance ID from Content if Content
        instance is referred instead
        """
        catalog_log = f"Catalog template {catalog_instance['@id']}"
        admin_id = catalog_instance.get("ProjectAdminIntanceID")
        # Adding the following code in case the typo is fixed
        if admin_id is None:
            admin_id = catalog_instance.get("ProjectAdminInstanceID")
        if admin_id is None:
            logger.error(
                f"{catalog_log} does not contain `ProjectContentIn(s)tanceID` field"
            )
            return
        admin_id = admin_id.get("@id")
        if (
            admin_id is not None
            and admin_id not in self.admin_ids
            and admin_id in self.content_ids
        ):
            logger.warning(
                f"{catalog_log} refers to Content Instance instead of Admin, trying to fetch Admin..."
            )
            content = self.client.get_template_instance(admin_id).json()
            admin_id = content["Other"]["Project Admin Instance ID"][
                "Project Admin Instance ID"
            ].get("@value")
        elif (
            admin_id is not None
            and admin_id not in self.admin_ids
            and admin_id not in self.content_ids
        ):
            logger.warning(
                f"{catalog_log} has an unexpected Admin reference: {admin_id}"
            )
        return admin_id

    def _get_and_validate_datasets(
        self, catalog_instance: Dict, instance_id: str
    ) -> List:
        datasets_list = catalog_instance.get("datasetIdentifier")
        if datasets_list is None:
            datasets_list = catalog_instance.get("datasetMetadataInstanceIdentifier")
        datasets = [ds.get("@id") for ds in datasets_list]
        datasets_validated = datasets.copy()
        for data_set in datasets:
            if not data_set:
                logger.warning(
                    f"Dataset reference in Catalog {catalog_instance['@id']} is empty"
                )
            elif not data_set.startswith(self.client.base_url):
                logger.warning(
                    f"Unexpected dataset link: {data_set}, Catalog ID {instance_id}; skipping"
                )
                datasets_validated.remove(data_set)
            elif data_set not in self.dataset_ids:
                logger.warning(
                    f"Dataset {data_set} is not an instance of the latest Dataset Template"
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
                distr_id = distr.get("@id")
                if distr_id:
                    linked_dist.append(
                        {"dataset_id": dataset_id, "distribution_id": distr_id}
                    )
                    dist_validation_list.append(distr_id)
                else:
                    logger.warning(
                        f"Dataset {dataset_id} contains no links to Distributions"
                    )

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
        data_frame = self._normalize_template_link_columns(
            data_frame, "distribution_id"
        )
        data_frame = self._normalize_template_link_columns(data_frame, "dataset_id")
        self.overall_mapping = pd.merge(
            self.overall_mapping, data_frame, how="outer", on="dataset_id"
        )

    def merge_content_data(self, portal_df):
        """For each instance of Content Template searches for focus area, keywords, themes and description"""
        content_data_dicts = []
        for content_instance_id in self.content_ids:
            content_templ_json = self.client.get_template_instance(
                content_instance_id
            ).json()
            content_dict = {"content_instance_id": content_instance_id, "keyword": []}
            scope = content_templ_json["Scope"]
            # get focus area
            focus_area = scope["Focus Area"]["Focus Area"]
            content_dict["focus_area_id"] = focus_area.get("@id")
            if content_dict["focus_area_id"] is None:
                logger.warning(
                    f"No Focus Area specified for Content Template {content_instance_id}, skipping instance"
                )
                continue
            fa_label = focus_area.get("rdfs:label")
            content_dict["focus_area"] = fa_label
            # get reference to Admin template
            admin_reference = content_templ_json["Other"]["Project Admin Instance ID"][
                "Project Admin Instance ID"
            ].get("@value")
            if admin_reference is None:
                logger.warning(
                    f"Content template {content_instance_id} does not refer to an Admin instance, skipping"
                )
                continue
            content_dict["admin_instance_id"] = admin_reference
            # save other focus area to keywords
            if fa_label == "other":
                content_dict["keyword"].append(
                    scope["Focus Area"]["Other Focus Area"].get("@value")
                )
            # get content id title
            content_title = [
                item["Project Title"].get("@value")
                for item in content_templ_json["Project Title"]
                if item["Project Title"].get("@value") is not None
            ]
            if content_title:
                content_dict["content_title"] = "; ".join(content_title)
            # get keywords and themes
            keywords = []
            themes = []
            self.collect_content_scope_data(scope, keywords, themes)
            content_dict["keyword"] += keywords
            content_dict["theme"] = themes
            content_data_dicts.append(content_dict)
        contents_df = pd.DataFrame(data=content_data_dicts)
        contents_df = self._normalize_template_link_columns(
            contents_df, "admin_instance_id"
        )
        combined_dataframe = pd.merge(
            self.overall_mapping, contents_df, how="outer", on="admin_instance_id"
        )
        # Create a table with admin instances and merge other mappings table
        admin_df = pd.DataFrame(data={"admin_instance_id": self.admin_ids})
        admin_df = pd.merge(admin_df, portal_df, how="left", on="admin_instance_id")
        combined_dataframe = pd.merge(
            admin_df, combined_dataframe, how="outer", on="admin_instance_id"
        )
        self._validate_content_mapping(combined_dataframe)
        # explode admin subject link in case of multiple descriptions
        combined_dataframe["count"] = combined_dataframe.groupby(
            ["admin_instance_id"], dropna=False
        )["description"].transform("nunique")
        combined_dataframe.loc[
            (combined_dataframe["count"].astype(int) > 1)
            & (pd.notnull(combined_dataframe["admin_graph_id"])),
            "admin_graph_id",
        ] = (
            combined_dataframe["admin_graph_id"].astype(str)
            + "#"
            + combined_dataframe.groupby(["admin_instance_id"], dropna=False)[
                "description"
            ]
            .transform("cumcount")
            .astype(str)
        )
        combined_dataframe.loc[
            pd.isnull(combined_dataframe["description"]), "description"
        ] = combined_dataframe["content_title"]

        combined_dataframe = self._validate_focus_area(combined_dataframe)
        combined_dataframe = self._validate_admin_mapping(combined_dataframe)
        return combined_dataframe

    def _normalize_template_link_columns(self, dataframe, column_name):
        """Function to fix most frequent mistakes in a link to dataset:
        - completes an ID with base URL if only ID is provided
        - removes search parameters such as ?folder
        - corrects slashes etc
        """
        # 90c508ec-1936-4d58-8d83-677e866bf6b6
        id_pattern = re.compile(
            "[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}"
        )
        dataframe[column_name] = dataframe[column_name].apply(
            lambda x: f"{self.client.base_url}/template-instances/{x}"
            if re.match(id_pattern, str(x))
            else x
        )
        dataframe[column_name] = dataframe[column_name].apply(
            lambda x: str(x).split("?")[0] if pd.notnull(x) else x
        )
        dataframe[column_name] = dataframe[column_name].apply(
            lambda x: np.nan if x == "" else x
        )
        dataframe[column_name] = dataframe[column_name].apply(
            lambda x: w3lib.url.canonicalize_url(x).replace("///", "//")
            if pd.notnull(x) and str(x).startswith("http")
            else x
        )
        return dataframe

    def _validate_content_mapping(self, dataframe):
        incorrect_admin_ref = dataframe.loc[
            pd.notnull(dataframe["admin_instance_id"])
            & (~dataframe["admin_instance_id"].isin(self.admin_ids))
        ]
        if not incorrect_admin_ref.empty:
            content_adm = incorrect_admin_ref[
                ["admin_instance_id", "content_instance_id"]
            ].to_dict("records")
            logger.warning(
                f"An Admin template reference is not an Admin Template instance for the following "
                f"Content templates: "
            )
            for record in content_adm:
                logger.warning(
                    f"Content instance {record['content_instance_id']} refers to "
                    f"{record['admin_instance_id']} instead of Admin Instance, please check"
                )

    @staticmethod
    def _validate_admin_mapping(dataframe):
        no_description = dataframe.loc[
            pd.isnull(dataframe["content_instance_id"])
            | pd.isnull(dataframe["description"])
        ]
        if not no_description.empty:
            logger.warning(
                f"Following Admin template was not referred from a Content template and will be removed:"
            )
            logger.warning(
                f"{', '.join(no_description['admin_instance_id'].dropna().values)}"
            )
            dataframe = dataframe.loc[
                pd.notnull(dataframe["content_instance_id"])
                | pd.notnull(dataframe["description"])
            ]
        return dataframe

    @staticmethod
    def _validate_focus_area(dataframe):
        """Validates if focus area and focus area id are one-to-one correspondence"""
        invalid_fa = dataframe.loc[
            (
                dataframe.index.isin(
                    dataframe.drop_duplicates(
                        subset=["focus_area", "focus_area_id"]
                    ).index
                )
            )
            & (
                ~dataframe.index.isin(
                    dataframe.drop_duplicates(subset=["focus_area"]).index
                )
            )
        ]
        if not invalid_fa.empty:
            fa_in_question = dataframe.loc[
                dataframe["focus_area_id"].isin(invalid_fa["focus_area_id"])
                | dataframe["focus_area"].isin(invalid_fa["focus_area"])
            ][["focus_area_id", "focus_area"]].drop_duplicates()

            invalid_records = invalid_fa.to_dict("records")
            for record in invalid_records:
                focus_area_id = record["focus_area_id"]
                focus_area = record["focus_area"]
                logger.warning(
                    f"Unexpected combination of focus area id and label {focus_area_id}: "
                    f"{focus_area}"
                )
                correct_id = fa_in_question.loc[
                    (fa_in_question["focus_area"] == focus_area)
                    & (fa_in_question["focus_area_id"] != focus_area_id),
                    "focus_area_id",
                ].unique()
                if correct_id.shape[0] == 1:
                    correct_id = correct_id[0]
                    logger.info(f"Replacing {focus_area_id} with {correct_id}")
                    dataframe.loc[
                        dataframe["focus_area"] == focus_area, "focus_area_id"
                    ] = correct_id
        return dataframe

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
