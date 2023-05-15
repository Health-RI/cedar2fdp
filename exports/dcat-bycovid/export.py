from pathlib import Path
from typing import List, Tuple, Union

import yaml
from rdflib import DCAT, DCTERMS, RDF, Graph, URIRef
from rdflib.term import Node

from cedar.client import CedarClient
from core.logger import get_logger

logger = get_logger()

ROOT_DIR = Path(__file__).parents[2]

ADMIN_TEMPLATE_MAPPING = {
    "http://purl.org/dc/terms/title": (
        "https://schema.metadatacenter.org/properties/78d03cd1-21ef-41f2-ad99-69bd1118af13",
        "https://schema.metadatacenter.org/properties/9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc",
        "https://schema.metadatacenter.org/properties/a48e48af-7e98-4174-9d1d-5a7b7cf0b788",
        "http://purl.org/dc/elements/1.1/title",
    ),
    "urn:creator": (
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
    mapping_table: dict, subj: URIRef, graph: Graph, export_graph: Graph
) -> None:
    """Maps target predicate and resource predicate chain values"""
    for target_predicate, mapping in mapping_table.items():
        temp_subject = subj
        obj_list = []
        result = get_object_recursively(mapping, temp_subject, graph, obj_list)

        if not result:
            raise LookupError(
                f"Could not find target value for predicate chain {mapping}"
            )
        for node in result:
            export_graph.add((subj, URIRef(target_predicate), node))


def build_export_graph(subj: URIRef, resource: str) -> Graph:
    # load resource (template instance)
    source_graph = Graph().parse(data=resource, format="json-ld")
    subject = URIRef(subj)
    export_graph = Graph()
    export_graph.bind("dcterms", DCTERMS)
    export_graph.bind("dcat", DCAT)
    export_graph.add((subject, RDF.type, DCAT.Dataset))
    # find triples based on mapping
    find_target_predicate_chain_values(
        ADMIN_TEMPLATE_MAPPING, subject, source_graph, export_graph
    )
    return export_graph


def main():
    config = yaml.safe_load(open(Path(ROOT_DIR, "config.yml"), "r"))
    client = CedarClient(api_key=config["cedar"]["apikey"])

    admin_template = (
        "https://repo.metadatacenter.org/templates/337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac"
    )
    content_template = (
        "https://repo.metadatacenter.org/templates/908e33e2-9485-4a93-ab22-1688dc5819dc"
    )
    catalog_template = (
        "https://repo.metadatacenter.org/templates/28d58a30-1a42-4715-a742-d2f46690563e"
    )
    dataset_template = (
        "https://repo.metadatacenter.org/templates/de169781-7f75-4aef-a0cb-ac435fe3a4c7"
    )
    dist_template = (
        "https://repo.metadatacenter.org/templates/22925909-9fb2-4ac8-a986-6db5ae7049e7"
    )

    adm_instances = {}

    # for adm_instance_id in client.search_instances(admin_template[-36:]):
    #     adm_instances[adm_instance_id] = Graph().parse(data=client.get_template_instance(adm_instance_id),
    #     format="json-ld")
    #
    # content_instances = {}
    # for content_instance_id in client.search_instances(content_template[-36:]):
    #     content_instances[content_instance_id] = Graph().parse(data=client.get_template_instance(content_instance_id),
    #     format="json-ld")
    #
    # print(f"found {len(adm_instances)} admin instances")
    # print(f"found {len(content_instances)} content instances")

    # test multiple instance: f0c065e2-10e3-4b3d-aca1-c4a9be0dce93
    # covid portal instance: 5994ae62-4163-4a92-b7b5-98e669d4a743
    subject = "https://repo.metadatacenter.org/template-instances/f0c065e2-10e3-4b3d-aca1-c4a9be0dce93"
    resource = client.get_template_instance(subject)

    export = build_export_graph(URIRef(subject), resource)

    logger.info(export.serialize())


if __name__ == "__main__":
    main()
