"""
Contains utility functions for Cedar-to-FDP export
"""

from typing import List, Tuple, Union

from rdflib import Graph, URIRef
from rdflib.term import BNode, Literal, Node

from core.logger import get_logger

logger = get_logger()


def implement_recursion(
    mapping: Tuple,
    parent_subject: Union[URIRef, Node],
    graph: Graph,
    obj_list: List,
    related_predicate: str = None,
) -> List[Tuple]:
    """
    Recursively walks over a graph along a tuple of predicates and saves terminal leaves to a list of tuples,
    first value in a tuple is target value, second value - a value for related property (e.g. language) or None
    Parameters
    ----------
    mapping: Tuple
        A predicates chain
    parent_subject: URIRef or Node
        A starting node
    graph: Graph
        A source graph to walk over
    obj_list: List
        A list to store results
    related_predicate: str or None
        A predicate for a related property, e.g. language, default is None
    Returns
    -------
    List[Tuple]
        A list of tuples with first value as target value and second is None or related property
    """
    for index, predicate_chain_node in enumerate(mapping):
        child_nodes = list(
            graph.triples((parent_subject, URIRef(predicate_chain_node), None))
        )
        for node in child_nodes:
            (child_subject, child_predicate, child_object) = node
            if predicate_chain_node == mapping[-1]:
                related = None
                if related_predicate is not None:
                    related_nodes = list(
                        graph.objects(parent_subject, URIRef(related_predicate))
                    )
                    if related_nodes:
                        related = related_nodes[0]
                obj_list.append((child_object, related))
            else:
                implement_recursion(
                    mapping=mapping[index + 1 : :],
                    parent_subject=child_object,
                    graph=graph,
                    obj_list=obj_list,
                    related_predicate=related_predicate,
                )
    return obj_list


def get_object_recursively(
    mapping: Tuple,
    parent_subject: Union[URIRef, Node],
    graph: Graph,
    related_predicate: str = None,
) -> List[Tuple]:
    """A wrapper for implement_recursion function"""
    results_list = []
    implement_recursion(
        mapping=mapping,
        parent_subject=parent_subject,
        graph=graph,
        obj_list=results_list,
        related_predicate=related_predicate,
    )
    return results_list


def update_language(
    value: Tuple[Literal, URIRef, None], instance_id: str = None
) -> Literal:
    """
    Updates _language for a Literal
    Parameters
    ----------
    value: Tuple
        A pair of literal to update and a language to set
    instance_id: str, Optional
        Cedar instance ID for debug
    Returns
    ------
    Literal
    """
    expected_languages = ["en", "nl"]
    debug_instance = ""
    if instance_id is not None:
        debug_instance = f", cedar ID {instance_id}"
    resulting_literal = None
    if value:
        resulting_literal = value[0]
        language = value[1]
        if isinstance(language, BNode):
            logger.warning(
                f'No relevant language provided for value "{resulting_literal}"{debug_instance}'
            )
            language = None
        if language is not None:
            language = language.rsplit("/", maxsplit=1)[-1]
            if language not in expected_languages:
                logger.warning(
                    f'Unexpected language "{language}" for title "{resulting_literal}"'
                    f"{debug_instance}, please check"
                )
            resulting_literal = Literal(resulting_literal, lang=language)
    return resulting_literal
