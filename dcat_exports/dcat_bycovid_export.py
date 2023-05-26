import re
from collections import OrderedDict
from datetime import datetime

import pandas as pd
import yaml
from rdflib import DCAT, DCTERMS, RDF, RDFS, Graph, URIRef
from rdflib.term import BNode, Literal

from cedar.client import CedarClient
from core.logger import get_logger
from dcat_exports.cedar_source_data import CedarAdminInstance
from dcat_exports.export_utils import get_object_recursively
from models.bycovid_models import DCATDataSet

logger = get_logger()

ADMIN_TEMPLATE_MAPPING = {
    "http://purl.org/dc/terms/title": (
        "https://schema.metadatacenter.org/properties/78d03cd1-21ef-41f2-ad99-69bd1118af13",
        "https://schema.metadatacenter.org/properties/9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc",
        "https://schema.metadatacenter.org/properties/a48e48af-7e98-4174-9d1d-5a7b7cf0b788",
        "http://purl.org/dc/elements/1.1/title",
    ),
    "http://purl.org/dc/terms/creator": (
        "https://schema.metadatacenter.org/properties/e7f6696a-4e6b-491f-9429-23037579452e",
        "https://schema.metadatacenter.org/properties/6455acbe-f02d-4628-8748-b3e98649076c",
        "https://schema.metadatacenter.org/properties/fe7e40b0-8c55-4221-bc82-399e80d19846",
    ),
    "language": (
        "https://schema.metadatacenter.org/properties/78d03cd1-21ef-41f2-ad99-69bd1118af13",
        "https://schema.metadatacenter.org/properties/9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc",
        "https://schema.metadatacenter.org/properties/a48e48af-7e98-4174-9d1d-5a7b7cf0b788",
        "http://def.isotc211.org/iso19115/2003/IdentificationInformation#MD_DataIdentification.language",
    ),
    "http://www.w3.org/ns/dcat#contactPoint": (
        "https://schema.metadatacenter.org/properties/83257c93-74ba-484b-bae7-8395ca8057a3",
        "https://schema.metadatacenter.org/properties/49cd19d7-5543-4ff5-9861-20e74ce7cfaa",
        "https://schema.metadatacenter.org/properties/ae358774-2e66-40e3-8856-d6d373a180f5",
    ),
    # ("http://purl.org/dc/terms/temporal", "http://purl.org/dc/terms/PeriodOfTime",
    # "http://www.w3.org/ns/dcat#startDate")
    "start": (
        "https://schema.metadatacenter.org/properties/792cb92d-dd83-4b0c-b0ba-6392913c9b09",
        "https://schema.metadatacenter.org/properties/44d6b2d1-24fa-4ee2-85ff-c9bc8565bddc",
        "https://schema.metadatacenter.org/properties/bbca9d8b-a95d-4239-a259-fb40164e5715",
    ),
    # ("http://purl.org/dc/terms/temporal", "http://purl.org/dc/terms/PeriodOfTime",
    # "http://www.w3.org/ns/dcat#endDate")
    "end": (
        "https://schema.metadatacenter.org/properties/792cb92d-dd83-4b0c-b0ba-6392913c9b09",
        "https://schema.metadatacenter.org/properties/44d6b2d1-24fa-4ee2-85ff-c9bc8565bddc",
        "https://schema.metadatacenter.org/properties/e6ba0001-590d-4400-a296-683dee6bf72a",
    ),
}
CONTENT_TEMPLATE_MAPPING = {
    "http://purl.org/dc/terms/title": (
        "https://schema.metadatacenter.org/properties/b7f01529-b4ca-4e67-a541-a111c9e60a63",
        "http://purl.org/dc/elements/1.1/title",
    ),
    "http://purl.org/dc/terms/created": ("http://purl.org/pav/createdOn",),
    "http://purl.org/dc/terms/modified": ("http://purl.org/pav/lastUpdatedOn",),
    "http://www.w3.org/ns/dcat#contactPoint": (
        "https://schema.metadatacenter.org/properties/bf746fc0-2d59-476a-b630-6d704e1a8caf",
        "https://schema.metadatacenter.org/properties/9bf17f4d-df28-4db3-92d3-16d4c2821f6d",
        "https://schema.metadatacenter.org/properties/fe7e40b0-8c55-4221-bc82-399e80d19846",
    ),
}

DIST_MAPPING = {
    # "datasetDate": ("http://purl.org/dc/terms/issued"),
    "http://purl.org/dc/terms/format": ("http://purl.org/dc/terms/conformsTo",),
    # "distributionMediaType": "http://www.w3.org/ns/dcat#mediaType",
    # "title": "http://purl.org/dc/terms/title",
    # "accessService": "http://www.w3.org/ns/dcat#accessService",
    "http://purl.org/dc/terms/description": ("http://purl.org/dc/terms/description",),
    "http://purl.org/dc/terms/license": ("http://purl.org/dc/terms/license",),
    "http://www.w3.org/ns/dcat#accessURL": ("http://www.w3.org/ns/dcat#accessURL",),
}

ADMIN_TEMPLATE = (
    "https://repo.metadatacenter.org/templates/337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac",
)
CONTENT_TEMPLATE = (
    "https://repo.metadatacenter.org/templates/908e33e2-9485-4a93-ab22-1688dc5819dc",
)
CATALOG_TEMPLATE = (
    "https://repo.metadatacenter.org/templates/28d58a30-1a42-4715-a742-d2f46690563e",
)
DATASET_TEMPLATE = (
    "https://repo.metadatacenter.org/templates/de169781-7f75-4aef-a0cb-ac435fe3a4c7",
)
DIST_TEMPLATE = (
    "https://repo.metadatacenter.org/templates/22925909-9fb2-4ac8-a986-6db5ae7049e7",
)

FOCUS_AREA_MAPPING = (
    "https://schema.metadatacenter.org/properties/7cb60a0c-4931-454a-8fca-1fd3faa8462f",
    "https://schema.metadatacenter.org/properties/40a3e466-85b3-429e-bf27-ccb31bf3c667",
    "https://schema.metadatacenter.org/properties/d6df6cc7-9902-430f-910f-096ae895e3fe",
)
CATALOG_TO_ADMIN_MAPPING = (
    "https://schema.metadatacenter.org/properties/bf746fc0-2d59-476a-b630-6d704e1a8caf",
    "https://schema.metadatacenter.org/properties/d9ff53e9-7762-4b0b-a466-c750148b3baa",
    "https://schema.metadatacenter.org/properties/7e519671-cb71-4bb9-8540-49989f5ca3db",
)

# (0000-000(?:1-[5-9]|2-[0-9]|3-[0-4])\d{3}-\d{3}[\dX]?)|(0009-00[0-1](?:[0-9]-[0-9])\d{3}-\d{3}[\dX]?)


# ORCID iDs are typically the 16-digit identifiers are assigned between 0000-0001-5000-0007 and 0000-0003-5000-0001,
# or between 0009-0000-0000-0000 and 0009-0010-0000-0000. "X" can be at the end.
ORCID_PATTERN = re.compile(
    "^https?:\/\/orcid\.org\/((0000-000(?:1-[5-9]|2-[0-9]|3-[0-4])\d{3}-\d{3}[\dX]?)|(0009-00[0-1](?:[0-9]-[0-9])\d{"
    "3}-\d{3}[\dX]?))"
)


class CedarFieldError(Exception):
    pass


def find_target_predicate_chain_values(
    mapping_table: dict,
    source_subject: URIRef,
    target_subject: URIRef,
    graph: Graph,
    export: Graph,
) -> None:
    for target_predicate, mapping in mapping_table.items():
        result = [
            record[0]
            for record in get_object_recursively(mapping, source_subject, graph)
        ]

        if result is None:
            raise CedarFieldError(
                f"Could not find target value for predicate chain {mapping}"
            )
        for node in result:
            export.add((target_subject, URIRef(target_predicate), node))


def query_dataset(graph):
    # def query_sparql(client: CedarClient, template_id):
    #     resource = client.get_template_instance(template_id)
    #     graph = Graph().parse(data=resource, format="json-ld")
    query = """
    PREFIX p: <https://schema.metadatacenter.org/properties/>
    PREFIX dcterms: <http://purl.org/dc/terms/>
    PREFIX dc: <http://purl.org/dc/elements/1.1/>
    PREFIX dcat: <http://w3.org/ns/dcat#>

    CONSTRUCT {
        ?s
            dcterms:title ?title ;
            dcterms:creator ?orcid .
    } WHERE {
        ?s
            p:78d03cd1-21ef-41f2-ad99-69bd1118af13/p:9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc/p:a48e48af-7e98-4174-9d1d-5a7b7cf0b788/dc:title ?title ;
            p:e7f6696a-4e6b-491f-9429-23037579452e/p:6455acbe-f02d-4628-8748-b3e98649076c/p:fe7e40b0-8c55-4221-bc82-399e80d19846 ?orcid .
    }
    """
    result = graph.query(query)

    return result


def get_focus_area(content_instance_id, graph):
    focus_areas = get_object_recursively(
        mapping=FOCUS_AREA_MAPPING,
        parent_subject=URIRef(content_instance_id),
        graph=graph,
    )

    if len(focus_areas) != 1:
        raise CedarFieldError(
            f"Catalog {content_instance_id} contains more than 1 focus area"
        )
    focus_area = focus_areas[0][0]
    return focus_area


def get_links_to_admin(content_instance_id, graph):
    admin_template_id = None
    x_list = get_object_recursively(
        mapping=CATALOG_TO_ADMIN_MAPPING,
        parent_subject=URIRef(content_instance_id),
        graph=graph,
    )
    if x_list:
        admin_template_id = x_list[0][0]
    else:
        logger.warning(
            f"Content template instance {content_instance_id} does not contain a link to its admin template instance"
        )
    return admin_template_id


def map_content_to_focus_area(
    client: CedarClient, admin_to_content_mapping: dict, td
) -> dict:
    """For each instance of Content Template searches for focus area"""
    content_template_id = CONTENT_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    catalogs = OrderedDict()
    # for index, admin_instance_id in enumerate(
    #     client.search_instances(content_template_id)
    # ):
    #     t = client.get_template_json(admin_instance_id)
    #     print(t["@id"])
    #     if t["@id"] in td["related_content_id"].values:
    #         pass
    w = []
    for content_instance_id in client.search_instances(content_template_id):
        if content_instance_id in [
            "https://repo.metadatacenter.org/template-instances/28350645-507f-404d-a9cb-e0b646d129bd",
            "https://repo.metadatacenter.org/template-instances/0c06df81-70fd-427f-b894-55830bb172f5",
            "https://repo.metadatacenter.org/template-instances/1e636018-2806-4807-b781-5835d5435b1f",
            "https://repo.metadatacenter.org/template-instances/db1d53d4-3ec0-4a5b-901e-3fe7d33214ec",
            "https://repo.metadatacenter.org/template-instances/3e270d85-a989-46da-a67c-eddc89e96c8f",
        ]:
            pass

        content_templ_json = client.get_template_instance(content_instance_id).json()

        content_instance = client.get_template_instance_jsonld(content_instance_id)
        graph = Graph().parse(data=content_instance, format="json-ld")

        focus_area = get_focus_area(content_instance_id, graph)

        content_dict = {"content_instance_id": content_instance_id}
        content_dict["keyword"] = []
        content_dict["theme"] = []

        if focus_area not in catalogs:
            catalogs[focus_area] = {
                "content_instances": [],
                "label": graph.value(subject=URIRef(focus_area), predicate=RDFS.label),
            }
        scope = content_templ_json["Scope"]
        for item in scope["Area Level"]:
            al = item["Area Level"]
            if al:
                area_level_theme = al.get("@id")
                area_level_keyword = al.get("@value")
                content_dict["keyword"].append(area_level_keyword)
                content_dict["theme"].append(area_level_theme)

        for item in scope["Care Setting"]:
            cs = item["Care Setting"]
            if cs:
                area_level_theme = cs.get("@id")
                area_level_keyword = cs.get("@value")
                content_dict["keyword"].append(area_level_keyword)
                content_dict["theme"].append(area_level_theme)

        for item in scope["Population Group"]:
            pg = item["Population Group"]
            if pg:
                area_level_theme, area_level_keyword = pg.values()
                content_dict["keyword"].append(area_level_keyword)
                content_dict["theme"].append(area_level_theme)
            key_w = item["Other Population Group"].get("@value")
            if key_w:
                content_dict["keyword"].append(key_w)

        if graph.value(subject=URIRef(focus_area), predicate=RDFS.label) == Literal(
            "other", datatype=URIRef("http://www.w3.org/2001/XMLSchema#string")
        ):
            other_fa = content_templ_json["Scope"]["Focus Area"][
                "Other Focus Area"
            ].get("@value")
            if other_fa is not None:
                content_dict["keyword"].append(other_fa)
        content_dict["focus_area"] = graph.value(
            subject=URIRef(focus_area), predicate=RDFS.label
        )
        catalogs[focus_area]["content_instances"].append(content_instance_id)

        admin_template_id = get_links_to_admin(content_instance_id, graph)
        if admin_template_id is not None:
            content_dict["admin_instance_id"] = admin_template_id
            w.append(content_dict)
            admin_to_content_mapping[f"{admin_template_id}"] = content_instance_id
    w_df = pd.DataFrame(data=w)
    td = pd.merge(td, w_df, how="outer", on="content_instance_id")

    return catalogs, td


def get_catalog_id(
    admin_instance_id, admin_to_content_mapping, content_to_catalog_mapping
):
    catalog_id = None
    content_id = admin_to_content_mapping.get(admin_instance_id)
    if content_id is not None:
        catalog_id = content_to_catalog_mapping.get(content_id)
        if catalog_id is None:
            logger.warning(
                f"content instance id {content_id} was not mapped to a catalog"
            )
    else:
        logger.warning(
            f"admin instance id {admin_instance_id} was not mapped to a content instance"
        )
    return catalog_id


def export_admin_data_to_dataset(admin_instance, subject):
    title = admin_instance.get_title(
        ADMIN_TEMPLATE_MAPPING["http://purl.org/dc/terms/title"],
        language_predicate=ADMIN_TEMPLATE_MAPPING["language"][-1],
    )
    creator = admin_instance.get_attribute(
        ADMIN_TEMPLATE_MAPPING["http://purl.org/dc/terms/creator"]
    )
    for creator_item in creator:
        if not ORCID_PATTERN.fullmatch(creator_item) and not isinstance(
            creator_item, BNode
        ):
            logger.error(
                f"Unexpected creator value: {creator_item}, Admin Template Id: {admin_instance.admin_instance_id}"
            )

    dates = admin_instance.get_pared_attributes(
        ADMIN_TEMPLATE_MAPPING["start"], ADMIN_TEMPLATE_MAPPING["end"][-1]
    )
    if not dates:
        start_date, end_date = None, None
    else:
        start_date, end_date = dates[0]
    primary_contact = admin_instance.get_attribute(
        ADMIN_TEMPLATE_MAPPING["http://www.w3.org/ns/dcat#contactPoint"]
    )

    dataset = DCATDataSet(
        uri=subject,
        title=title,
        creator=creator,
        start_date=start_date,
        end_date=end_date,
        contact_point=primary_contact,
    ).to_graph()
    return dataset


def write_datasets(
    client: CedarClient,
    export: Graph,
    content_to_catalog_mapping: dict,
    admin_to_content_mapping: dict,
    map_table: pd.DataFrame,
) -> None:
    admin_template_id = ADMIN_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    for index, admin_instance_id in enumerate(
        client.search_instances(admin_template_id)
    ):
        admin_instance = CedarAdminInstance(admin_instance_id, client)
        # admin_instance = client.get_template_instance(admin_instance_id)
        # graph = Graph().parse(
        #     data=admin_instance, format="json-ld", publicID="https://orcid.org"
        # )
        #
        subject = URIRef(f"http://example.com/dataset/{index}")
        # start = datetime.now()

        # export.add((subject, RDF.type, DCAT.Dataset))
        # query source
        # dataset = query_dataset(graph=admin_instance.graph_data)
        # #
        # for s, p, o in dataset.graph:
        #     export.add((subject, p, o))
        # or find the same values recursively
        #

        dataset = export_admin_data_to_dataset(admin_instance, subject)

        ds_table = map_table.loc[
            map_table["admin_instance_id"] == Literal(admin_instance.admin_instance_id)
        ][["description", "publisher", "keyword", "theme"]]
        if not ds_table.empty:
            if ds_table.shape[0] > 1:
                print("too many rows!!!!!")
            s = ds_table.to_dict("records")[0]
            descr = s["description"]
            if pd.notnull(descr):
                dataset.add((subject, DCTERMS.description, Literal(descr)))
            publ = s["publisher"]
            if pd.notnull(publ):
                dataset.add((subject, DCTERMS.publisher, URIRef(publ)))
            kw = s["keyword"]
            if kw:
                keywords = [i for i in kw if pd.notnull(i)]
                for k in keywords:
                    dataset.add((subject, DCAT.keyword, Literal(k)))
            themes = s["theme"]
            if themes:
                th = [i for i in themes if pd.notnull(i)]
                for t in th:
                    dataset.add((subject, DCAT.theme, URIRef(t)))

        # for title in self.title:
        #     graph.add((subject, DCTERMS.title, title))

        export += dataset
        # find_target_predicate_chain_values(
        #     mapping_table=ADMIN_TEMPLATE_MAPPING,
        #     source_subject=URIRef(admin_instance_id),
        #     target_subject=subject,
        #     graph=admin_instance.graph_data,
        #     export=export,
        # )
        # end = datetime.now()
        # print(end - start)

        catalog_id = get_catalog_id(
            admin_instance_id, admin_to_content_mapping, content_to_catalog_mapping
        )
        if catalog_id is not None:
            export.add((catalog_id, DCAT.dataset, subject))


def get_resulting_catalog_mapping(catalogs):
    catalog_values = [item["content_instances"] for item in catalogs.values()]

    resulting_catalog_mapping = {
        content_inst: URIRef(f"http://example.com/catalog/{catalog_values.index(lst)}")
        for lst in catalog_values
        for content_inst in lst
    }
    return resulting_catalog_mapping


def write_dist(client, export):
    template_id = DIST_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]
    for index, instance_id in enumerate(client.search_instances(template_id)):
        dist_instance = client.get_template_instance_jsonld(instance_id)
        dist_graph = Graph().parse(data=dist_instance, format="json-ld")
        subject = URIRef(f"http://example.com/distribution/{index}")
        export.add((subject, RDF.type, DCAT.Distribution))
        find_target_predicate_chain_values(
            mapping_table=DIST_MAPPING,
            source_subject=URIRef(instance_id),
            target_subject=subject,
            graph=dist_graph,
            export=export,
        )


def build_export_graph(client):
    export_graph = Graph()
    # bind namespaces
    export_graph.bind("dcat", DCAT)
    export_graph.bind("dcterms", DCTERMS)

    template_id = CATALOG_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]
    catalog_temp_instances = []
    for index, instance_id in enumerate(client.search_instances(template_id)):
        dist_instance = client.get_template_instance(instance_id).json()
        project_id_field_name = "ProjectContentIntanceID"
        project_id = dist_instance.get(project_id_field_name)
        if project_id is None or isinstance(project_id, dict):
            project_id_field_name = "projectIdentifier"
        description = dist_instance["catalogDescription"].get("@value")
        datasets = [ds.get("@id") for ds in dist_instance["datasetIdentifier"]]
        for d in datasets:
            if d is not None and not d.startswith("https://repo.metadatacenter.org"):
                logger.warning(
                    f"Unexpected dataset link: {d}, Catalog ID {instance_id}"
                )
        instance_dict = {
            "catalog_instance_id": dist_instance["@id"],
            "content_instance_id": dist_instance[project_id_field_name][0]["@id"],
            "description": description,
            "publisher": dist_instance["publisher"].get("@id"),
            "dataset_id": datasets,
        }
        catalog_temp_instances.append(instance_dict)

        if description is None or description == "":
            logger.error(f"Empty catalog description: {instance_id}")

    catalog_temp_instances_df = pd.DataFrame(data=catalog_temp_instances).explode(
        "dataset_id"
    )

    linked_dist = []
    for ds_id in catalog_temp_instances_df["dataset_id"].values:
        if ds_id is not None and ds_id.startswith("https://repo.metadatacenter.org"):
            dataset_json = client.get_template_instance(ds_id).json()
            field_name = "DistributionMetadataInstanceID"
            distr = dataset_json.get(field_name)
            if distr is None:
                field_name = "datasetDistributionIdentifier"
                distr = dataset_json.get(field_name)
            #'DistributionMetadataInstanceID' "datasetDistributionIdentifier"
            distributions = [dist["@id"] for dist in distr]
            linked_dist += distributions
        # else:
        #     logger.warning(f"Unexpected dataset link: {ds_id}, Catalog ID {}")
    ds_t = DATASET_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]
    datasets_via_api = client.search_instances(ds_t)
    missing_ds = [
        d
        for d in catalog_temp_instances_df["dataset_id"].unique()
        if d is not None and d.startswith("https://repo.metadatacenter.org")
    ]
    if missing_ds:
        new_line = "\n"
        logger.warning(
            f"Following datasets are not referenced from a catalog: {f',{new_line}'.join(missing_ds)}"
        )

    template_id = DIST_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]
    all_dist = client.search_instances(template_id)
    missed = [i for i in all_dist if i not in linked_dist]
    if missed:
        new_line = "\n"
        logger.warning(
            f"Following distributions are not referenced from a catalog: {f',{new_line}'.join(missed)}"
        )

    admin_to_content_mapping = {}
    catalogs, cross_template_mapping = map_content_to_focus_area(
        client=client,
        admin_to_content_mapping=admin_to_content_mapping,
        td=catalog_temp_instances_df,
    )
    resulting_catalog_mapping = get_resulting_catalog_mapping(catalogs=catalogs)

    catalogs_dict_view_list = list(catalogs.items())
    for item in catalogs_dict_view_list:
        subject = URIRef(
            f"http://example.com/catalog/{catalogs_dict_view_list.index(item)}"
        )
        export_graph.add((subject, RDF.type, DCAT.Catalog))
        export_graph.add((subject, DCTERMS.title, item[1]["label"]))
        export_graph.add((subject, DCAT.theme, URIRef(item[0])))

    write_datasets(
        client=client,
        export=export_graph,
        content_to_catalog_mapping=resulting_catalog_mapping,
        admin_to_content_mapping=admin_to_content_mapping,
        map_table=cross_template_mapping,
    )

    write_dist(
        client=client,
        export=export_graph,
    )

    return export_graph


def export_dcat():
    config = yaml.safe_load(open("../config.yml", "r"))
    client = CedarClient(api_key=config["cedar"]["apikey"])
    # test multiple instance: f0c065e2-10e3-4b3d-aca1-c4a9be0dce93
    # covid portal instance: 5994ae62-4163-4a92-b7b5-98e669d4a743
    # query_sparql(client, template_id="65cf949f-96e3-4310-ad5b-965002683835")
    export = build_export_graph(client=client)
    export.serialize(
        destination=f"../example-output/{datetime.now().date()}_output.ttl"
    )
    print(export.serialize())


if __name__ == "__main__":
    export_dcat()
