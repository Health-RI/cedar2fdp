import re
from datetime import datetime

import pandas as pd
import yaml
from rdflib import DCAT, DCTERMS, FOAF, RDF, XSD, Graph, URIRef
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

DIST_MAPPING = {
    # "datasetDate": ("http://purl.org/dc/terms/issued"),
    "http://purl.org/dc/terms/format": ("http://purl.org/dc/terms/conformsTo",),
    # "distributionMediaType": "http://www.w3.org/ns/dcat#mediaType",
    "http://purl.org/dc/terms/title": ("http://purl.org/dc/terms/title",),
    # "accessService": "http://www.w3.org/ns/dcat#accessService",
    "http://purl.org/dc/terms/description": ("http://purl.org/dc/terms/description",),
    "http://purl.org/dc/terms/license": ("http://purl.org/dc/terms/license",),
    "http://www.w3.org/ns/dcat#accessURL": ("http://www.w3.org/ns/dcat#accessURL",),
}

BY_COVID_URI = URIRef("https://covid19initiatives.health-ri.nl")

# ORCID iDs are typically the 16-digit identifiers are assigned between 0000-0001-5000-0007 and 0000-0003-5000-0001,
# or between 0009-0000-0000-0000 and 0009-0010-0000-0000. "X" can be at the end.
ORCID_PATTERN = re.compile(
    "^https?:\/\/orcid\.org\/((0000-000(?:1-[5-9]|2-[0-9]|3-[0-4])\d{3}-\d{3}[\dX]?)|(0009-00[0-1](?:[0-9]-[0-9])\d{"
    "3}-\d{3}[\dX]?))"
)


class ByCovidConfig(metaclass=CedarConfig):
    admin_templ_id = "337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac"
    catalog_templ_id = "28d58a30-1a42-4715-a742-d2f46690563e"
    content_templ_id = "908e33e2-9485-4a93-ab22-1688dc5819dc"
    dataset_templ_id = "de169781-7f75-4aef-a0cb-ac435fe3a4c7"
    distribution_templ_id = "22925909-9fb2-4ac8-a986-6db5ae7049e7"


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


def export_admin_data_to_dataset(admin_instance, subject, catalog_dict):
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

    publisher = catalog_dict["publisher"]
    if pd.notnull(publisher):
        publisher = URIRef(publisher)
    else:
        publisher = None
    keywords = []
    kw = catalog_dict["keyword"]
    if kw and isinstance(kw, list):
        keywords = [Literal(i) for i in kw if pd.notnull(i)]
    theme = []
    themes = catalog_dict["theme"]
    if themes and isinstance(kw, list):
        theme = [URIRef(i) for i in themes if pd.notnull(i)]

    dataset = DCATDataSet(
        uri=subject,
        title=title,
        creator=creator,
        description=Literal(catalog_dict["description"]),
        start_date=start_date,
        end_date=end_date,
        contact_point=primary_contact,
        publisher=publisher,
        keyword=keywords,
        theme=theme,
    )
    return dataset


def write_datasets(
    client: CedarClient,
    export: Graph,
    map_table: pd.DataFrame,
) -> None:

    map_table = map_table[
        [
            "admin_instance_id",
            "admin_graph_id",
            "description",
            "publisher",
            "keyword",
            "theme",
            "content_graph_id",
        ]
    ].dropna(subset=["admin_graph_id"], axis="rows")
    admin_ids = map_table["admin_instance_id"].unique()

    for admin_instance_id in admin_ids:
        admin_instance = CedarAdminInstance(admin_instance_id, client)

        ds_table = map_table.loc[
            map_table["admin_instance_id"] == admin_instance.admin_instance_id
        ][
            [
                "admin_graph_id",
                "description",
                "publisher",
                "keyword",
                "theme",
                "content_graph_id",
            ]
        ].drop_duplicates(
            subset=["admin_graph_id", "description"]
        )
        ds_list_of_records = ds_table.to_dict("records")
        for record in ds_list_of_records:
            subject = URIRef(record["admin_graph_id"])
            dataset = export_admin_data_to_dataset(admin_instance, subject, record)
            if str(dataset.title).startswith("TEST-"):
                continue
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
    distr_ids = (
        mapping_table.loc[
            pd.notnull(mapping_table["admin_graph_id"])
            & pd.notnull(mapping_table["distribution_id"]),
            "distribution_id",
        ]
        .drop_duplicates()
        .values
    )
    for index, instance_id in enumerate(distr_ids):
        dataset = mapping_table.loc[
            mapping_table["distribution_id"] == instance_id, "admin_graph_id"
        ].values
        subject = URIRef(f"http://example.com/distribution/{index}")
        export.add((URIRef(dataset[0]), DCAT.distribution, subject))
        dist_instance = client.get_template_instance_jsonld(instance_id)
        dist_graph = Graph().parse(data=dist_instance, format="json-ld")
        export.add((subject, RDF.type, DCAT.Distribution))
        find_target_predicate_chain_values(
            mapping_table=DIST_MAPPING,
            source_subject=URIRef(instance_id),
            target_subject=subject,
            graph=dist_graph,
            export=export,
        )


def write_top_level(export):
    """Adds top-level Catalog pointing to Covid-19 portal"""
    by_covid_uri = BY_COVID_URI
    title = "COVID-19 related data initiatives - Project overview"
    description = (
        "Health-RI launched the Dutch COVID-19 Data Support Programme to support investigators and "
        "health care professionals with tools and services in their search for ways to overcome the "
        "pandemic and its' health consequences. \n"
        "To facilitate and stimulate an integrated health data infrastructure, Health-RI facilitates "
        "investigators by connecting communities, providing data services and tools, and presenting an "
        "overview of COVID-19 related initiatives, provided on this site."
    )
    issued = datetime.now().date()
    keywords = ["COVID-19"]
    homepage = "https://covid19initiatives.health-ri.nl/p/ProjectOverview"

    export.bind("foaf", FOAF)
    export.add((by_covid_uri, RDF.type, DCAT.Catalog))
    export.add((by_covid_uri, DCTERMS.title, Literal(title)))
    export.add((by_covid_uri, DCTERMS.description, Literal(description)))
    export.add((by_covid_uri, DCTERMS.issued, Literal(issued, datatype=XSD.date)))
    for keyword in keywords:
        export.add((by_covid_uri, DCAT.keyword, Literal(keyword)))
    export.add((by_covid_uri, FOAF.homepage, URIRef(homepage)))


def build_export_graph(client):
    export_graph = Graph()
    # bind namespaces
    export_graph.bind("dcat", DCAT)
    export_graph.bind("dcterms", DCTERMS)

    write_top_level(export_graph)

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
                    datatype=XSD.string,
                ),
            )
        )
        export_graph.add((subject, DCAT.theme, URIRef(item["focus_area_id"])))
        export_graph.add((BY_COVID_URI, DCAT.catalog, subject))

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
    export.serialize(
        destination=f"../example-output/{datetime.now().date()}_output.xml"
    )
    print(export.serialize())


if __name__ == "__main__":
    export_dcat()
