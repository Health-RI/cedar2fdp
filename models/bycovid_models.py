"""Pydantic models for FDP objects"""
from typing import List, Optional, Union

from pydantic import BaseModel, Field, validator
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCAT, DCTERMS, RDF, XSD

from core.logger import get_logger

logger = get_logger()

VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")


class VCard(BaseModel):
    full_name: Optional[Literal]
    uid: URIRef


def add_empty_node_of_type(graph, subject, predicate, node_type=None):
    node = BNode()
    graph.add((subject, predicate, node))
    if node_type:
        graph.add((node, RDF.type, node_type))
    return node


class DCATDataSet(BaseModel):
    """DCAT Dataset model"""

    uri: URIRef
    title: List[Literal]
    description: Literal
    creator: Union[List[URIRef], List[VCard]]
    start_date: Optional[Literal]
    end_date: Optional[Literal]
    contact_point: Union[List[URIRef], List[VCard]]
    publisher: Optional[URIRef]
    keyword: Optional[List[Literal]] = Field(default_factory=list)
    theme: Optional[List[URIRef]] = Field(default_factory=list)

    @validator("creator", "contact_point")
    def validate_empty_nodes(cls, field_value, values, field):
        """Checks if a list contains empty BNodes and removes them"""
        if any(isinstance(creator_item, BNode) for creator_item in field_value):
            logger.warning(
                f"One or more {field.name} instances are empty BNode objects {values['uri']}, removing"
            )
            field_value = [item for item in field_value if not isinstance(item, BNode)]
        return field_value

    def to_graph(self, userinfo_format: str = None) -> Graph:
        """Converts class instance to dcat dataset graph"""
        graph = Graph()
        subject = URIRef(self.uri)
        # For dcterms:identifier
        identifier = subject.rsplit("/", maxsplit=1)[-1]

        graph.add(
            (subject, DCTERMS.identifier, Literal(identifier, datatype=XSD.token))
        )
        graph.add((subject, RDF.type, DCAT.Dataset))
        for title in self.title:
            graph.add((subject, DCTERMS.title, title))
        self.add_vcard_info(
            attribute_name="creator",
            graph=graph,
            subject=subject,
            predicate=DCTERMS.creator,
            userinfo_format=userinfo_format,
        )
        self.add_vcard_info(
            attribute_name="contact_point",
            graph=graph,
            subject=subject,
            predicate=DCAT.contactPoint,
            userinfo_format=userinfo_format,
        )
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
        if userinfo_format == "vcard":
            graph.bind("v", VCARD)

        return graph

    def add_vcard_info(
        self, attribute_name, graph, subject, predicate, userinfo_format: str = None
    ) -> None:
        """
        Adds person information as URIRef or VCard node
        Parameters
        ----------
        attribute_name: String
            A class attribute to add to graph;
        graph: Graph
            A graph to add data
        subject:
        predicate:
        userinfo_format:
        Returns
        ------
        None
        """
        attribute = getattr(self, attribute_name)

        if userinfo_format != VCARD.VCard and all(type(x) for x in attribute) == VCard:
            logger.warning(f"Items of '{attribute_name}' attribute are in VCard format")
        if attribute:
            if userinfo_format == VCARD.VCard:
                for item in attribute:
                    vcard_node = add_empty_node_of_type(
                        graph=graph,
                        subject=subject,
                        predicate=predicate,
                        node_type=userinfo_format,
                    )
                    graph.add((vcard_node, VCARD.fn, item.full_name))
                    graph.add((vcard_node, VCARD.hasUID, item.uid))
            else:
                for item in attribute:
                    if isinstance(item, VCard):
                        item = item.uid
                    graph.add((subject, predicate, item))
        else:
            add_empty_node_of_type(
                graph=graph,
                subject=subject,
                predicate=predicate,
                node_type=userinfo_format,
            )
