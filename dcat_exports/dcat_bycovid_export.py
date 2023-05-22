from collections import OrderedDict

import yaml
from rdflib import DCAT, DCTERMS, RDF, RDFS, Graph, URIRef

from cedar.client import CedarClient
from core.logger import get_logger
from dcat_exports.export_utils import get_object_recursively, update_language
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


def write_catalogs(client: CedarClient, admin_to_content_mapping: dict) -> dict:
    """For each instance of content template searches for focus area"""
    content_template_id = CONTENT_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    catalogs = OrderedDict()

    for content_instance_id in client.search_instances(content_template_id):
        content_instance = client.get_template_instance(content_instance_id)
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


def write_datasets(
    client: CedarClient,
    export: Graph,
    content_to_catalog_mapping: dict,
    admin_to_content_mapping: dict,
) -> None:
    admin_template_id = ADMIN_TEMPLATE[0].rsplit("/", maxsplit=1)[-1]

    for index, admin_instance_id in enumerate(
        client.search_instances(admin_template_id)
    ):
        admin_instance = client.get_template_instance(admin_instance_id)
        graph = Graph().parse(
            data=admin_instance, format="json-ld", publicID="https://orcid.org"
        )

        subject = URIRef(f"http://example.com/dataset/{index}")
        # start = datetime.now()

        export.add((subject, RDF.type, DCAT.Dataset))
        # query source
        # dataset = query_dataset(graph=graph)
        # #
        # for s, p, o in dataset.graph:
        #     export.add((subject, p, o))
        # or find the same values recursively
        #

        title = get_object_recursively(
            ADMIN_TEMPLATE_MAPPING["http://purl.org/dc/terms/title"],
            URIRef(admin_instance_id),
            graph,
            ADMIN_TEMPLATE_MAPPING["language"][-1],
        )

        creator = get_object_recursively(
            ADMIN_TEMPLATE_MAPPING["http://purl.org/dc/terms/creator"],
            URIRef(admin_instance_id),
            graph,
        )

        full_title = [
            update_language(title_tuple, admin_instance_id) for title_tuple in title
        ]
        dataset = DCATDataSet(
            uri=subject, title=full_title, creator=[record[0] for record in creator]
        ).to_graph()
        export += dataset
        # find_target_predicate_chain_values(
        #     mapping_table=ADMIN_TEMPLATE_MAPPING,
        #     source_subject=URIRef(admin_instance_id),
        #     target_subject=subject,
        #     graph=graph,
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


def build_export_graph(client):
    export_graph = Graph()
    # bind namespaces
    export_graph.bind("dcat", DCAT)
    export_graph.bind("dcterms", DCTERMS)
    admin_to_content_mapping = {}
    catalogs = write_catalogs(
        client=client,
        admin_to_content_mapping=admin_to_content_mapping,
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
    )
    return export_graph


def export_dcat():
    config = yaml.safe_load(open("../config.yml", "r"))
    client = CedarClient(api_key=config["cedar"]["apikey"])
    # test multiple instance: f0c065e2-10e3-4b3d-aca1-c4a9be0dce93
    # covid portal instance: 5994ae62-4163-4a92-b7b5-98e669d4a743
    # query_sparql(client, template_id="65cf949f-96e3-4310-ad5b-965002683835")
    export = build_export_graph(client=client)
    # with open(f"../example-output/{datetime.now().date()}_output.ttl", "w") as f:
    #     f.write(export.serialize())
    print(export.serialize())


if __name__ == "__main__":
    export_dcat()
