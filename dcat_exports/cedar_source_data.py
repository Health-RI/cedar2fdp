"""
A class to query data from Admin Template Instance
"""
from typing import List, Tuple

from rdflib import Graph, URIRef

from cedar.client import CedarClient
from dcat_exports.export_utils import get_object_recursively, update_language


class CedarAdminInstance:
    def __init__(self, admin_instance_id: str, client: CedarClient):
        self.admin_instance_id = admin_instance_id
        self.graph_data = self.get_and_parse_instance(client)

    def get_and_parse_instance(self, client: CedarClient) -> Graph:
        """Queries a template instance and parses it to a rdflib.Graph"""
        admin_instance = client.get_template_instance_jsonld(self.admin_instance_id)
        return Graph().parse(
            data=admin_instance, format="json-ld", publicID="https://orcid.org"
        )

    def get_title(self, mapping: Tuple, language_predicate: str) -> List:
        """Gets title-language pairs from sours and converts to a list of literals with defined language"""
        title = self.get_pared_attributes(mapping, language_predicate)
        full_title = [
            update_language(title_tuple, self.admin_instance_id)
            for title_tuple in title
        ]
        return full_title

    def get_attribute(self, mapping: Tuple) -> List:
        """Gets an Admin Instance attribute by mapping"""
        attribute = get_object_recursively(
            mapping, URIRef(self.admin_instance_id), self.graph_data
        )
        if attribute:
            attribute = [record[0] for record in attribute]
        return attribute

    def get_pared_attributes(
        self, first_attribute_mapping: Tuple, second_mapping: str
    ) -> List[Tuple]:
        """Gets a pair of Admin Instance attributes diverged at a node before the leave"""
        data = get_object_recursively(
            first_attribute_mapping,
            URIRef(self.admin_instance_id),
            self.graph_data,
            second_mapping,
        )
        return data
