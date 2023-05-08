import yaml
from cedar.client import Client
from fdp import Client as FDPClient
from rdflib import Graph, URIRef, Literal, BNode, RDF, DCAT, DCTERMS, FOAF


def post_cedar_instance_to_fdp(
    cedar_client: Client, template_id: str, config: dict
) -> None:
    client = FDPClient("https://health-ri.sandbox.semlab-leiden.nl")
    client.login(config["fdp"]["username"], config["fdp"]["password"])

    count = 0

    for resource in cedar_client.search_instances(template_id):
        print(f"{count}: {resource}")
        tpl_instance = cedar_client.get_template_instance(resource)
        foo = Graph().parse(data=tpl_instance, format="json-ld")

        # FIXME workarounds
        s = URIRef(resource)
        # FIXME FDP expects a rdf:type
        foo.add((s, RDF.type, DCAT.Resource))
        # FIXME FDP expects a parent link
        foo.add(
            (s, DCTERMS.isPartOf, URIRef("https://health-ri.sandbox.semlab-leiden.nl"))
        )
        # FIXME dcat:Resource expects a dct:title
        foo.add((s, DCTERMS.title, Literal(f"Test {count} (hardcoded title value)")))
        # FIXME dcat:Resource expects a dct:publisher
        p = BNode()
        foo.add((p, RDF.type, FOAF.Agent))
        foo.add((p, FOAF.name, Literal("me")))
        foo.add((s, DCTERMS.publisher, p))
        # FIXME dcat:Resource expects a version
        foo.add((s, DCTERMS.hasVersion, Literal(1)))

        try:
            client.post(resource_type="project-admin", metadata=foo)
        except:
            print(f"  failed {resource}")

        count += 1


if __name__ == "__main__":
    config = yaml.safe_load(open("config.yml", "r"))

    client = Client(api_key=config["cedar"]["apikey"])
    covid_admin_template = "337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac"
    post_cedar_instance_to_fdp(client, covid_admin_template, config)
