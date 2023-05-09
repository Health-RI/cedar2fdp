# export.py
import yaml
from cedar.client import Client
from rdflib import Graph, URIRef, Literal, BNode, RDF, DCAT, DCTERMS, FOAF

if __name__=='__main__':
    config = yaml.safe_load(open('config.yml', 'r'))
    client = Client(api_key=config['cedar']['apikey'])
    resource = client.get_template_instance('https://repo.metadatacenter.org/template-instances/5994ae62-4163-4a92-b7b5-98e669d4a743')

    m = {
        "http://purl.org/dc/terms/title": {
            "https://schema.metadatacenter.org/properties/b7f01529-b4ca-4e67-a541-a111c9e60a63": "http://purl.org/dc/elements/1.1/title"
        }
    }

    # load resource (template instance)
    g = Graph().parse(data=resource,format='json-ld')
    s = URIRef(resource)
    export = Graph()
    export.add((s, RDF.type, DCAT.Dataset))

    # find triples based on mapping
    for target_predicate,mapping in m.items():
        for k,v in mapping.items():
            element_instance = g.value(subject=s, predicate=URIRef(k))
            target_title = g.value(subject=element_instance, predicate=URIRef(v))
            print(target_title)
            export.add((s, URIRef(target_predicate), target_title))

    print(export.serialize())
