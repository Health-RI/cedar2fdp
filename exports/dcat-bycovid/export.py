import yaml
from cedar.client import Client
from rdflib import Graph, URIRef, Literal, BNode, RDF, DCAT, DCTERMS, FOAF

if __name__=='__main__':
    config = yaml.safe_load(open('../../config.yml', 'r'))
    client = Client(api_key=config['cedar']['apikey'])
    subject = "https://repo.metadatacenter.org/template-instances/5994ae62-4163-4a92-b7b5-98e669d4a743"
    resource = client.get_template_instance(subject)

    mapping_table = {
        "http://purl.org/dc/terms/title": ( "https://schema.metadatacenter.org/properties/b7f01529-b4ca-4e67-a541-a111c9e60a63", "http://purl.org/dc/elements/1.1/title" ),
        "http://purl.org/dc/terms/created": ( "http://purl.org/pav/createdOn", ),
        "http://purl.org/dc/terms/modified": ( "http://purl.org/pav/lastUpdatedOn", )
    }

    # load resource (template instance)
    g = Graph().parse(data=resource, format='json-ld')
    s = URIRef(subject)
    export = Graph()
    export.bind("dcterms", DCTERMS)
    export.bind("dcat", DCAT)
    export.add((s, RDF.type, DCAT.Dataset))

    # find triples based on mapping
    for target_predicate, mapping in mapping_table.items():
        temp_subject = s
        temp_object = None

        for predicate_chain_node in mapping:
            temp_object = g.value(subject=temp_subject, predicate=URIRef(predicate_chain_node))
            temp_subject = temp_object

        if temp_object is None:
            raise Exception(f"Could not find target value for predicate chain {mapping}")

        export.add((s, URIRef(target_predicate), temp_object))

    print(export.serialize())
