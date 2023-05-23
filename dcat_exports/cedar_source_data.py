"""

"""
from typing import Tuple

from rdflib import Graph, URIRef

from dcat_exports.export_utils import get_object_recursively, update_language


class CedarAdminInstance:
    def __init__(self, admin_instance_id, client):
        self.admin_instance_id = admin_instance_id
        self.graph_data = self.get_and_parse_instance(client)

    def get_and_parse_instance(self, client):
        admin_instance = client.get_template_instance(self.admin_instance_id)
        return Graph().parse(
            data=admin_instance, format="json-ld", publicID="https://orcid.org"
        )

    def get_title(self, mapping, language_predicate):
        title = self.get_pared_attributes(mapping, language_predicate)
        full_title = [
            update_language(title_tuple, self.admin_instance_id)
            for title_tuple in title
        ]
        return full_title

    def get_attribute(self, mapping):
        attribute = get_object_recursively(
            mapping, URIRef(self.admin_instance_id), self.graph_data
        )
        if attribute:
            attribute = [record[0] for record in attribute]
        return attribute

    def get_pared_attributes(self, first_attribute_mapping: Tuple, second_mapping: str):
        data = get_object_recursively(
            first_attribute_mapping,
            URIRef(self.admin_instance_id),
            self.graph_data,
            second_mapping,
        )
        return data
