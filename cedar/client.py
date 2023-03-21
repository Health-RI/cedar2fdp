import requests

class Client():
    def __init__(self, api_key: str, endpoint: str ='https://repo.metadatacenter.org') -> None:
        self.endpoint = endpoint
        self.headers = {'Authorization': f'apiKey {api_key}'}

    def get_template(self, id: str) -> dict:
        r = requests.get(f'{self.endpoint}/templates/{id}', headers=self.headers)
        return Template(src=r.json())

    def get_template_instance(self, id: str) -> dict:
        r = requests.get(f'{self.endpoint}/template-instances/{id}', headers=self.headers) #TODO format?
        return r.json() # defaults to json-ld

class Schema:
    def __init__(self, **kwargs) -> None:
        self.src = kwargs.get('src')
        self.key = kwargs.get('key', None)
        self.parent = kwargs.get('parent', None)

    def get_title(self, key: str = "title"):
        return self.src.get(key, f'**{key} not present in {self.key}: {self.src}')

    def get_predicate(self, key: str = None) -> str:
        _key = key or self.key
        # try to resolve field in our own context
        if 'properties' in self.src and '@context' in self.src['properties']:
            contextProperties = self.src['properties']['@context']['properties']
            if _key in contextProperties:
                return contextProperties[_key]['enum'][0]

        # if not found, delegate to parent
        if self.parent:
            return self.parent.get_predicate(_key)

from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, DCTERMS
SH = Namespace('http://www.w3.org/ns/shacl#')

class Shape:
    def write(self, graph: Graph, node: URIRef = None, rel: URIRef = SH.property) -> None:
        pass

class Template(Schema, Shape):
    def get_fields(self):
        types = {
            'https://schema.metadatacenter.org/core/TemplateField': TemplateField,
            'https://schema.metadatacenter.org/core/StaticTemplateField': StaticTemplateField,
            'https://schema.metadatacenter.org/core/TemplateElement': TemplateElement
        }

        for field in self.src['properties']:
            sub = self.src['properties'][field]
            _type = sub.get('@type', None)

            #print(f'found type {_type} for {field}')

            if _type in types:
                yield types[_type](src=sub, key=field, parent=self)

    def write(self, graph: Graph, node: URIRef = None, rel: URIRef = SH.property) -> None:
        graph.bind('sh', SH)
        graph.bind('dcterms', DCTERMS)

        s = URIRef(self.src['@id'])
        graph.add((s, RDF.type, SH.NodeShape))

        for field in self.get_fields():
            field.write(graph, s)

class TemplateField(Schema, Shape):
    """CEDAR templatefield type."""
    def write(self, graph: Graph, node: URIRef = None, rel: URIRef = SH.property) -> None:
        s = BNode()
        graph.add((s, RDF.type, SH.PropertyShape))
        graph.add((s, SH.path, URIRef(self.get_predicate())))
        graph.add((s, SH.name, Literal(self.get_title('skos:prefLabel'))))

        if node:
            graph.add((node, rel, s))

class StaticTemplateField(Schema, Shape):
    """CEDAR static templatefield type."""

class TemplateElement(Schema, Shape):
    """CEDAR template element."""
