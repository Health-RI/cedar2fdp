from typing import List, Iterator
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS

from api.api_client import BasicAPIClient

SH = Namespace("http://www.w3.org/ns/shacl#")
DASH = Namespace("http://datashapes.org/dash#")


class CedarEndPoints:
    base = "https://repo.metadatacenter.org"
    base_resource = "https://resource.metadatacenter.org"
    templates = f"{base}/templates"
    template_instances = f"{base}/template-instances"
    search = f"{base_resource}/search"


class CedarClient(BasicAPIClient):
    """API client to connect to cedar API"""

    def __init__(self, api_key: str, base_url: str = CedarEndPoints.base):
        headers = {"Authorization": f"apiKey {api_key}"}
        super().__init__(base_url, headers)

    def get_template(self, template_id: str) -> "Template":
        """Gets template data by id and converts it to Template object"""
        path = f"{CedarEndPoints.templates}/{template_id}"
        response = self.get(path=path)
        return Template(src=response.json())

    def get_template_instance(self, template_instance_id: str) -> str:
        url = (
            template_instance_id
            if template_instance_id.startswith("https://")
            else f"{CedarEndPoints.template_instances}/{template_instance_id}"
        )
        response = self.get(path=url)
        return response.text  # defaults to json-ld

    def search_instances(self, template_id: str) -> List[str]:
        """Searches template instances belonging to a template with certain id
        returns a list of template instances ids"""
        response = self.get(
            path=CedarEndPoints.search,
            params={"is_based_on": f"{CedarEndPoints.templates}/{template_id}"},
        )
        return [resource["@id"] for resource in response.json()["resources"]]


class Schema:
    def __init__(self, **kwargs) -> None:
        self.src = kwargs.get("src")
        self.key = kwargs.get("key", None)
        self.parent = kwargs.get("parent", None)

    def get_title(self, key: str = "title") -> str:
        return self.src.get(key, f"**{key} not present in {self.key}: {self.src}")

    def get_predicate(self, key: str = None) -> str:
        _key = key or self.key
        # try to resolve field in our own context
        if "properties" in self.src and "@context" in self.src["properties"]:
            contextProperties = self.src["properties"]["@context"]["properties"]
            if _key in contextProperties:
                return contextProperties[_key]["enum"][0]

        # if not found, delegate to parent
        if self.parent:
            return self.parent.get_predicate(_key)

    def resolve_prefixed(self, pname: str) -> str:
        if ":" in pname:
            prefix, local_name = pname.split(":")
            if prefix in self.src["@context"]:
                ns = self.src["@context"][prefix]
                return ns + local_name

    def get_datatype(self) -> str:
        if "_ui" in self.src:
            return self.src["_ui"].get("inputType", None)

    def get_order(self, key: str = None) -> int:
        _key = key or self.key

        if "_ui" in self.src and "order" in self.src["_ui"]:
            return self.src["_ui"]["order"].index(_key)

        if self.parent:
            return self.parent.get_order(_key)


class Shape:
    def write(
        self,
        graph: Graph,
        node: URIRef = None,
        rel: URIRef = SH.property,
        group: URIRef = None,
    ) -> None:
        pass


class Template(Schema, Shape):
    def get_fields(self) -> Iterator[Schema]:
        types = {
            "https://schema.metadatacenter.org/core/TemplateField": TemplateField,
            "https://schema.metadatacenter.org/core/StaticTemplateField": StaticTemplateField,
            "https://schema.metadatacenter.org/core/TemplateElement": TemplateElement,
        }

        for field in self.src["properties"]:
            sub = self.src["properties"][field]

            # TODO make more robust
            if sub.get("type", None) == "array":
                sub = sub["items"]

            _type = sub.get("@type", None)

            if _type in types:
                yield types[_type](src=sub, key=field, parent=self)

    def write(
        self,
        graph: Graph,
        node: URIRef = None,
        rel: URIRef = SH.property,
        group: URIRef = None,
    ) -> None:
        graph.bind("sh", SH)
        graph.bind("dash", DASH)

        s = URIRef(self.src["@id"])
        graph.add((s, RDF.type, SH.NodeShape))
        graph.add((s, RDFS.label, Literal(self.get_title())))

        if not self.parent:
            graph.add((s, SH.targetSubjectsOf, URIRef("http://schema.org/isBasedOn")))

        for field in self.get_fields():
            field.write(graph, s, group=group)


class TemplateField(Schema, Shape):
    """CEDAR templatefield type."""

    def write(
        self,
        graph: Graph,
        node: URIRef = None,
        rel: URIRef = SH.property,
        group: URIRef = None,
    ) -> None:
        s = BNode()
        graph.add((s, RDF.type, SH.PropertyShape))
        graph.add((s, SH.path, URIRef(self.get_predicate())))
        graph.add((s, SH.name, Literal(self.get_title("skos:prefLabel"))))

        # data type
        dt = self.get_datatype()
        mapping = {
            "link": {
                "nodekind": SH.BlankNodeOrIRI,
                "viewer": DASH.URIViewer,
                "editor": DASH.URIEditor,
            },
            "textfield": {
                "nodekind": SH.BlankNodeOrLiteral,
                "viewer": DASH.LiteralViewer,
                "editor": DASH.LiteralEditor,
            },
            "temporal": {
                "stuff": ("_valueConstraints", "temporalType"),
                "viewer": DASH.LiteralViewer,
                "editor": DASH.LiteralEditor,
            },
            "numeric": {
                "stuff": ("_valueConstraints", "numberType"),
                "viewer": DASH.LiteralViewer,
                "editor": DASH.LiteralEditor,
            },
        }
        if dt in mapping:
            m = mapping[dt]
            if "nodekind" in m:
                # TODO fix this properly
                if dt == "textfield" and "branches" in self.src.get(
                    "_valueConstraints", {}
                ):
                    graph.add((s, SH.nodeKind, SH.BlankNodeOrIRI))
                else:
                    graph.add((s, SH.nodeKind, m["nodekind"]))
            elif "stuff" in m:
                k, v = m["stuff"]
                x = self.resolve_prefixed(self.src[k][v])
                graph.add((s, SH.datatype, URIRef(x)))

            graph.add((s, DASH.viewer, m["viewer"]))
            graph.add((s, DASH.editor, m["editor"]))

        # TODO cardinality

        order = self.get_order()
        if order:
            graph.add((s, SH.order, Literal(order)))

        if group:
            graph.add((s, SH.group, group))

        if node:
            graph.add((node, rel, s))


class StaticTemplateField(Schema, Shape):
    """CEDAR static templatefield type."""


class TemplateElement(Template):
    """CEDAR template element."""

    def write(
        self,
        graph: Graph,
        node: URIRef = None,
        rel: URIRef = SH.property,
        group: URIRef = None,
    ) -> None:
        grp = URIRef(self.src["@id"] + "#group")
        graph.add((grp, RDF.type, SH.PropertyGroup))
        graph.add((grp, RDFS.label, Literal(self.get_title())))

        # write ourselves as a property of our parent?
        s = BNode()
        graph.add((s, RDF.type, SH.PropertyShape))
        graph.add((s, SH.path, URIRef(self.get_predicate())))
        graph.add((s, SH.node, URIRef(self.src["@id"])))
        graph.add((s, SH.name, Literal(self.get_title())))
        graph.add((s, DASH.viewer, DASH.DetailsViewer))
        graph.add((s, DASH.editor, DASH.DetailsEditor))
        graph.add((node, rel, s))

        super().write(graph, node, rel, grp)
