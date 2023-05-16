from typing import List, Tuple, Union

import yaml
from rdflib import DCAT, DCTERMS, RDF, RDFS, Graph, URIRef
from rdflib.term import Node

from cedar.client import CedarClient
from core.logger import get_logger

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


def get_object_recursively(
    mapping: Tuple, parent_subject: Union[URIRef, Node], graph: Graph, obj_list: List
) -> List:
    """Recursively walks over a graph along a tuple of predicates and saves terminal leaves to a list"""
    for index, predicate_chain_node in enumerate(mapping):
        child_nodes = list(
            graph.triples((parent_subject, URIRef(predicate_chain_node), None))
        )
        for node in child_nodes:
            (child_subject, child_predicate, child_object) = node
            if predicate_chain_node == mapping[-1]:
                obj_list.append(child_object)
            else:
                get_object_recursively(
                    mapping=mapping[index + 1 : :],
                    parent_subject=child_object,
                    graph=graph,
                    obj_list=obj_list,
                )
    return obj_list


def find_target_predicate_chain_values(
    mapping_table: dict,
    source_subject: URIRef,
    target_subject: URIRef,
    graph: Graph,
    export: Graph,
) -> None:
    for target_predicate, mapping in mapping_table.items():
        obj_list = []
        result = get_object_recursively(mapping, source_subject, graph, obj_list)

        if result is None:
            raise Exception(
                f"Could not find target value for predicate chain {mapping}"
            )
        for node in result:
            export.add((target_subject, URIRef(target_predicate), node))


def write_catalogs(
    client: CedarClient, export: Graph, admin_to_content_mapping: dict
) -> dict:
    content_template_id = CONTENT_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    catalogs = {}

    for content_instance_id in client.search_instances(content_template_id):
        content_instance = client.get_template_instance(content_instance_id)
        graph = Graph().parse(data=content_instance, format="json-ld")

        obj_list = []
        get_object_recursively(
            mapping=FOCUS_AREA_MAPPING,
            parent_subject=URIRef(content_instance_id),
            graph=graph,
            obj_list=obj_list,
        )

        if len(obj_list) != 1:
            raise Exception(
                f"catalog {content_instance_id} contains more than 1 focus area"
            )
        focus_area = obj_list[0]

        if focus_area not in catalogs:
            catalogs[focus_area] = {
                "content_instances": [],
                "label": graph.value(subject=URIRef(focus_area), predicate=RDFS.label),
            }
        catalogs[focus_area]["content_instances"].append(content_instance_id)

        x_list = []
        get_object_recursively(
            mapping=CATALOG_TO_ADMIN_MAPPING,
            parent_subject=URIRef(content_instance_id),
            graph=graph,
            obj_list=x_list,
        )
        if len(x_list) == 0:
            logger.warning(
                f"content template instance {content_instance_id} does not contain a link to its admin template instance"
            )
            continue
        admin_template_id = x_list[0]

        admin_to_content_mapping[f"{admin_template_id}"] = content_instance_id

    resulting_catalog_mapping = {}

    count = 0
    for key, value in catalogs.items():
        subject = URIRef(f"http://example.com/catalog/{count}")

        count += 1

        export.add((subject, RDF.type, DCAT.Catalog))
        export.add((subject, DCTERMS.title, value["label"]))
        export.add((subject, DCAT.theme, URIRef(key)))

        for content_instance_id in value["content_instances"]:
            resulting_catalog_mapping[content_instance_id] = subject

    return resulting_catalog_mapping


def write_datasets(
    client: CedarClient,
    export: Graph,
    content_to_catalog_mapping: dict,
    admin_to_content_mapping: dict,
) -> None:
    admin_template_id = "337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac"

    for index, admin_instance_id in enumerate(
        client.search_instances(admin_template_id)
    ):
        admin_instance = client.get_template_instance(admin_instance_id)
        graph = Graph().parse(data=admin_instance, format="json-ld")

        subject = URIRef(f"http://example.com/dataset/{index}")

        export.add((subject, RDF.type, DCAT.Dataset))
        find_target_predicate_chain_values(
            mapping_table=ADMIN_TEMPLATE_MAPPING,
            source_subject=URIRef(admin_instance_id),
            target_subject=subject,
            graph=graph,
            export=export,
        )

        if admin_instance_id in admin_to_content_mapping:
            content_id = admin_to_content_mapping[admin_instance_id]

            if content_id in content_to_catalog_mapping:
                catalog_id = content_to_catalog_mapping[content_id]
                export.add((catalog_id, DCAT.dataset, subject))
            else:
                logger.warning(
                    f"content instance id {content_id} was not mapped to a catalog"
                )
        else:
            logger.warning(
                f"admin instance id {admin_instance_id} was not mapped to a content instance"
            )


def build_export_graph(client):
    export_graph = Graph()
    # bind namespaces in case they are not bound yet
    export_graph.bind("dcat", DCAT)
    export_graph.bind("dcterms", DCTERMS)
    admin_to_content_mapping = {}
    catalog_mapping = write_catalogs(
        client=client,
        export=export_graph,
        admin_to_content_mapping=admin_to_content_mapping,
    )
    write_datasets(
        client=client,
        export=export_graph,
        content_to_catalog_mapping=catalog_mapping,
        admin_to_content_mapping=admin_to_content_mapping,
    )
    return export_graph


def export_dcat():
    config = yaml.safe_load(open("../config.yml", "r"))
    client = CedarClient(api_key=config["cedar"]["apikey"])
    export = build_export_graph(client=client)
    print(export.serialize())


if __name__ == "__main__":
    export_dcat()
