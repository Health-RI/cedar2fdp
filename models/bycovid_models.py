"""Pydantic models for FDP objects"""
from typing import List, Union

from pydantic import BaseModel
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCAT, DCTERMS, RDF, XSD


class DCATDataSet(BaseModel):
    """DCAT Dataset model"""

    uri: URIRef
    title: Union[List[Literal]]
    creator: List[URIRef]

    def to_graph(self) -> Graph:
        """Converts class instance to dcat dataset graph"""
        graph = Graph()
        subject = URIRef(self.uri)
        # For dcterms:identifier
        if "#" in subject:
            identifier = subject.split("#")[-1]
        else:
            identifier = subject.split("/")[-1]

        graph.add(
            (subject, DCTERMS.identifier, Literal(identifier, datatype=XSD.token))
        )
        graph.add((subject, RDF.type, DCAT.Dataset))
        for title in self.title:
            graph.add((subject, DCTERMS.title, title))
        for creator in self.creator:
            graph.add((subject, DCTERMS.creator, creator))

        graph.bind("dcat", DCAT)
        graph.bind("dcterms", DCTERMS)

        return graph
