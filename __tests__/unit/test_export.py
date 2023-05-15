import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from rdflib import Graph, URIRef

from dcat_exports.dcat_bycovid_export import write_catalogs

ROOT_DIR = Path(__file__).parents[2]
INPUT_DIR = Path(ROOT_DIR, "./example-input")
OUTPUT_DIR = Path(ROOT_DIR, "./example-output")


def get_template_by_id(*args, **kwargs):
    templ_id = args[0].split("/")[-1]
    path = Path(INPUT_DIR, f"template_{templ_id}.json")
    with open(path, "r") as t_file:
        template_json_ld = json.loads(t_file.read())
    return template_json_ld


@pytest.mark.parametrize("cont_template_id", ["908e33e2-9485-4a93-ab22-1688dc5819dc"])
@patch("cedar.client.CedarClient")
def test_write_catalog(cedar_client, cont_template_id):
    # Set up
    cont_template_path = Path(INPUT_DIR, f"response_{cont_template_id}.json")
    with open(cont_template_path, "r") as templ_file:
        cont_template = json.loads(templ_file.read())
    cedar_client = Mock()
    cedar_client.search_instances.return_value = [
        resource["@id"] for resource in cont_template["resources"]
    ]
    cedar_client.get_template_instance.side_effect = get_template_by_id
    expected_path = Path(OUTPUT_DIR, f"catalog_{cont_template_id}.json")
    # Act
    with open(expected_path, "r") as dict_file:
        expected_dict = json.loads(dict_file.read())
    expected_dict = {key: URIRef(value) for key, value in expected_dict.items()}

    ex = Graph()
    admin_to_content_mapping = {}
    actual_dict = write_catalogs(
        client=cedar_client,
        export=ex,
        admin_to_content_mapping=admin_to_content_mapping,
    )
    # Assert
    assert actual_dict == expected_dict
