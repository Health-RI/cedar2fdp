from collections import OrderedDict
from datetime import datetime

from rdflib import DCAT, DCTERMS, RDFS, Graph, URIRef

from cedar.client import CedarClient
from core.logger import get_logger
from dcat_exports.export_controller import CedarFieldError
from dcat_exports.export_utils import get_object_recursively

logger = get_logger()


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

CONTENT_TEMPLATE = (
    "https://repo.metadatacenter.org/templates/908e33e2-9485-4a93-ab22-1688dc5819dc",
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

DIST_MAPPING = {
    # "datasetDate": ("http://purl.org/dc/terms/issued"),
    DCTERMS.format: ("http://purl.org/dc/terms/conformsTo",),
    # "distributionMediaType": "http://www.w3.org/ns/dcat#mediaType",
    DCTERMS.title: ("http://purl.org/dc/terms/title",),
    # "accessService": "http://www.w3.org/ns/dcat#accessService",
    DCTERMS.description: ("http://purl.org/dc/terms/description",),
    DCTERMS.license: ("http://purl.org/dc/terms/license",),
    DCAT.accessURL: ("http://www.w3.org/ns/dcat#accessURL",),
}


def map_content_to_focus_area(
    client: CedarClient, admin_to_content_mapping: dict
) -> dict:
    """For each instance of Content Template searches for focus area"""
    start = datetime.now()
    content_template_id = CONTENT_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    catalogs = OrderedDict()

    for content_instance_id in client.search_instances(content_template_id):

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


def get_resulting_catalog_mapping(catalogs):
    catalog_values = [item["content_instances"] for item in catalogs.values()]

    resulting_catalog_mapping = {
        content_inst: URIRef(f"http://example.com/catalog/{catalog_values.index(lst)}")
        for lst in catalog_values
        for content_inst in lst
    }
    return resulting_catalog_mapping


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

    CONSTRUCT { ?s dcterms:title ?title ; dcterms:creator ?orcid . } WHERE { ?s
    p:78d03cd1-21ef-41f2-ad99-69bd1118af13/p:9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc/p:a48e48af-7e98-4174-9d1d
    -5a7b7cf0b788/dc:title ?title ; p:e7f6696a-4e6b-491f-9429-23037579452e/p:6455acbe-f02d-4628-8748-b3e98649076c/p
    :fe7e40b0-8c55-4221-bc82-399e80d19846 ?orcid . }"""
    result = graph.query(query)

    return result


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
