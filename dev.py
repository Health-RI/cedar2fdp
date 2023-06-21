import yaml
from rdflib import DCAT, DCTERMS, FOAF, RDF, BNode, Graph, Literal, URIRef

from cedar.client import CedarClient
from core.logger import get_logger
from fdp.client import FDPClient

logger = get_logger()


def post_cedar_instance_to_fdp(
    cedar_client: CedarClient, template_id: str, config: dict
) -> None:
    fdp_base_url = config["fdp"]["base_url"]
    fdp_client = FDPClient(
        base_url=fdp_base_url,
        username=config["fdp"]["username"],
        password=config["fdp"]["password"],
    )

    cedar_template_instances = cedar_client.search_instances(template_id)

    for index, resource in enumerate(cedar_template_instances):
        logger.info(f"{index}: {resource}")
        tpl_instance = cedar_client.get_template_instance_jsonld(resource)
        foo = Graph().parse(data=tpl_instance, format="json-ld")

        # FIXME workarounds
        s = URIRef(resource)
        # FIXME FDP expects a rdf:type
        foo.add((s, RDF.type, DCAT.Resource))
        # FIXME FDP expects a parent link
        foo.add((s, DCTERMS.isPartOf, URIRef(fdp_base_url)))
        # FIXME dcat:Resource expects a dct:title
        foo.add((s, DCTERMS.title, Literal(f"Test {index} (hardcoded title value)")))
        # FIXME dcat:Resource expects a dct:publisher
        p = BNode()
        foo.add((p, RDF.type, FOAF.Agent))
        foo.add((p, FOAF.name, Literal("me")))
        foo.add((s, DCTERMS.publisher, p))
        # FIXME dcat:Resource expects a version
        foo.add((s, DCTERMS.hasVersion, Literal(1)))

        try:
            fdp_client.post_serialised(resource_type="project-admin", metadata=foo)
        except SystemExit:
            logger.error(f"Failed to upload resource: {resource}")


if __name__ == "__main__":
    config = yaml.safe_load(open("config.yml", "r"))

    client = CedarClient(api_key=config["cedar"]["apikey"])
    covid_admin_template = "337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac"
    post_cedar_instance_to_fdp(client, covid_admin_template, config)
