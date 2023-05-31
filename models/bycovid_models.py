"""Pydantic models for FDP objects"""
from typing import List, Optional, Union

from pydantic import BaseModel, Field
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCAT, DCTERMS, RDF, XSD


class DCATDataSet(BaseModel):
    """DCAT Dataset model"""

    uri: URIRef
    title: Union[List[Literal]]
    # todo make description mandatory
    description: Optional[Literal]
    creator: List[URIRef]
    start_date: Optional[Literal]
    end_date: Optional[Literal]
    contact_point: List[URIRef]
    publisher: Optional[URIRef]
    keyword: Optional[Literal] = Field(default_factory=list)
    theme: Optional[URIRef] = Field(default_factory=list)

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
        for contact in self.contact_point:
            graph.add((subject, DCAT.contactPoint, contact))
        # add date node
        date_node = BNode()
        graph.add((subject, DCTERMS.temporal, date_node))
        graph.add((date_node, RDF.type, DCTERMS.PeriodOfTime))
        if self.start_date:
            graph.add((date_node, DCAT.startDate, self.start_date))
        if self.end_date:
            graph.add((date_node, DCAT.endDate, self.end_date))

        if self.description:
            graph.add((subject, DCTERMS.description, self.description))
        if self.publisher:
            graph.add((subject, DCTERMS.publisher, self.publisher))
        for key_w in self.keyword:
            graph.add((subject, DCAT.keyword, key_w))
        for theme in self.theme:
            graph.add((subject, DCAT.theme, theme))

        graph.bind("dcat", DCAT)
        graph.bind("dcterms", DCTERMS)

        return graph
