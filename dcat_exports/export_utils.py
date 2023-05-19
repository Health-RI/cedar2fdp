from typing import List, Tuple, Union

from rdflib import Graph, URIRef
from rdflib.term import Node


def get_object_recursively(
    mapping: Tuple, parent_subject: Union[URIRef, Node], graph: Graph, obj_list: List
) -> List:
    """Recursively walks over a graph along a tuple of predicates and saves terminal leaves to a list"""
    for index, predicate_chain_node in enumerate(mapping):
        child_nodes = list(
            graph.triples((parent_subject, URIRef(predicate_chain_node), None))
        )
        for node in child_nodes:
            (child_subject, child_predicate, child_object) = node
            if predicate_chain_node == mapping[-1]:
                obj_list.append(child_object)
            else:
                get_object_recursively(
                    mapping=mapping[index + 1 : :],
                    parent_subject=child_object,
                    graph=graph,
                    obj_list=obj_list,
                )
    return obj_list
