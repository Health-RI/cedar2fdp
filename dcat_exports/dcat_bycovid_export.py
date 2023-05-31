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
from dcat_exports.export_controller import (
    CedarConfig,
    CedarFieldError,
    ExportController,
)
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
DATASET_TEMPLATE = (
    "https://repo.metadatacenter.org/templates/de169781-7f75-4aef-a0cb-ac435fe3a4c7",
)
DISTRIBUTION_TEMPLATE = "22925909-9fb2-4ac8-a986-6db5ae7049e7"

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


class ByCovidConfig(metaclass=CedarConfig):
    admin_templ_id = "337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac"
    catalog_templ_id = "28d58a30-1a42-4715-a742-d2f46690563e"
    content_templ_id = "908e33e2-9485-4a93-ab22-1688dc5819dc"
    dataset_templ_id = "de169781-7f75-4aef-a0cb-ac435fe3a4c7"
    distribution_templ_id = "22925909-9fb2-4ac8-a986-6db5ae7049e7"


# (0000-000(?:1-[5-9]|2-[0-9]|3-[0-4])\d{3}-\d{3}[\dX]?)|(0009-00[0-1](?:[0-9]-[0-9])\d{3}-\d{3}[\dX]?)


# ORCID iDs are typically the 16-digit identifiers are assigned between 0000-0001-5000-0007 and 0000-0003-5000-0001,
# or between 0009-0000-0000-0000 and 0009-0010-0000-0000. "X" can be at the end.
ORCID_PATTERN = re.compile(
    "^https?:\/\/orcid\.org\/((0000-000(?:1-[5-9]|2-[0-9]|3-[0-4])\d{3}-\d{3}[\dX]?)|(0009-00[0-1](?:[0-9]-[0-9])\d{"
    "3}-\d{3}[\dX]?))"
)


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
    start = datetime.now()
    content_template_id = CONTENT_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    catalogs = OrderedDict()

    for content_instance_id in client.search_instances(content_template_id):

        content_templ_json = client.get_template_instance(content_instance_id).json()

        content_instance = client.get_template_instance_jsonld(content_instance_id)
        graph = Graph().parse(data=content_instance, format="json-ld")

        focus_area = get_focus_area(content_instance_id, graph)

        if focus_area not in catalogs:
            catalogs[focus_area] = {
                "content_instances": [],
                "label": graph.value(subject=URIRef(focus_area), predicate=RDFS.label),
            }

        catalogs[focus_area]["content_instances"].append(content_instance_id)

        admin_template_id = get_links_to_admin(content_instance_id, graph)
        if admin_template_id is not None:
            admin_to_content_mapping[f"{admin_template_id}"] = content_instance_id

    stop = datetime.now()
    logger.info(f"Second: {stop - start}")

    return catalogs


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
    )
    return dataset


def write_datasets(
    client: CedarClient,
    export: Graph,
    map_table: pd.DataFrame,
) -> None:
    admin_template_id = ADMIN_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    for index, admin_instance_id in enumerate(
        client.search_instances(admin_template_id)
    ):
        admin_instance = CedarAdminInstance(admin_instance_id, client)

        subject = URIRef(f"http://example.com/dataset/{index}")

        dataset = export_admin_data_to_dataset(admin_instance, subject)

        ds_table = map_table.loc[
            map_table["admin_instance_id"] == admin_instance.admin_instance_id
        ][["description", "publisher", "keyword", "theme", "content_graph_id"]]
        # todo move to model
        if not ds_table.empty:
            if ds_table.shape[0] > 1:
                print("too many rows!!!!!")
            s = ds_table.to_dict("records")[0]
            descr = s["description"]
            if pd.notnull(descr):
                dataset.description = Literal(descr)
            publ = s["publisher"]
            if pd.notnull(publ):
                dataset.publisher = URIRef(publ)
            kw = s["keyword"]
            if kw and isinstance(kw, list):
                keywords = [Literal(i) for i in kw if pd.notnull(i)]
                dataset.keyword = keywords
            themes = s["theme"]
            if themes and isinstance(kw, list):
                theme = [URIRef(i) for i in themes if pd.notnull(i)]
                dataset.theme = theme

        export += dataset.to_graph()

        catalog_ids = ds_table["content_graph_id"].values
        if catalog_ids.shape[0] > 0 and pd.notnull(catalog_ids[0]):
            catalog_id = URIRef(catalog_ids[0])
            if pd.notnull(catalog_id):
                export.add((catalog_id, DCAT.dataset, subject))


def get_resulting_catalog_mapping(catalogs):
    catalog_values = [item["content_instances"] for item in catalogs.values()]

    resulting_catalog_mapping = {
        content_inst: URIRef(f"http://example.com/catalog/{catalog_values.index(lst)}")
        for lst in catalog_values
        for content_inst in lst
    }
    return resulting_catalog_mapping


def write_dist(client, export, mapping_table):
    for index, instance_id in enumerate(client.search_instances(DISTRIBUTION_TEMPLATE)):
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

    cedar_export = ExportController(client, ByCovidConfig)
    cedar_export.overall_mapping = cedar_export.get_catalogs_data()
    cedar_export.merge_datasets_distributions_ids()
    cedar_export.overall_mapping = cedar_export.merge_content_data()

    cedar_export.overall_mapping[
        "content_graph_id"
    ] = cedar_export.overall_mapping.groupby(
        ["focus_area_id", "focus_area"], dropna=True
    ).ngroup()
    cedar_export.overall_mapping["content_graph_id"] = cedar_export.overall_mapping[
        "content_graph_id"
    ].apply(
        lambda x: f"http://example.com/catalog/{str(int(x))}" if pd.notnull(x) else x
    )
    # catalog_df = cedar_export.overall_mapping.copy()
    # catalog_df = catalog_df[["focus_area_id", "focus_area", "@id"]].drop_duplicates().dropna()
    # catalog_df["@id"] = catalog_df["@id"].apply(lambda x: f"http://example.com/catalog/{str(int(x))}")
    # catalog_df = catalog_df.set_index("@id")
    # catalog_df.rename(columns={"focus_area_id": DCAT.theme, "focus_area": DCTERMS.title}, inplace=True)

    # namespace_manager = NamespaceManager(Graph())
    # namespace_manager.bind("dcat", DCAT)
    # namespace_manager.bind("dcterms", DCTERMS)
    #
    # g = rdfpandas.to_graph(catalog_df, namespace_manager)

    # catalogs_dict_view_list = list(catalogs.items())
    df = (
        cedar_export.overall_mapping.copy()[
            ["content_graph_id", "focus_area", "focus_area_id"]
        ]
        .dropna()
        .drop_duplicates()
    )
    content_items = df.to_dict("records")
    for item in content_items:
        subject = URIRef(item["content_graph_id"])
        export_graph.add((subject, RDF.type, DCAT.Catalog))
        export_graph.add(
            (
                subject,
                DCTERMS.title,
                Literal(
                    item["focus_area"],
                    datatype="http://www.w3.org/2001/XMLSchema#string",
                ),
            )
        )
        export_graph.add((subject, DCAT.theme, URIRef(item["focus_area_id"])))

    write_datasets(
        client=client,
        export=export_graph,
        map_table=cedar_export.overall_mapping,
    )

    write_dist(
        client=client, export=export_graph, mapping_table=cedar_export.overall_mapping
    )

    return export_graph


def export_dcat():
    config = yaml.safe_load(open("../config.yml", "r"))
    client = CedarClient(api_key=config["cedar"]["apikey"])
    export = build_export_graph(client=client)
    export.serialize(
        destination=f"../example-output/{datetime.now().date()}_output.ttl"
    )
    print(export.serialize())


if __name__ == "__main__":
    export_dcat()
