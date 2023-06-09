import difflib
from pathlib import Path
from unittest.mock import patch

import pytest
from colorama import Fore
from freezegun import freeze_time
from rdflib import DCAT, DCTERMS, Graph

from dcat_exports.cedar_source_data import CedarAdminInstance
from dcat_exports.dcat_bycovid_export import (
    export_admin_data_to_dataset,
    write_top_level,
)

ROOT_DIR = Path(__file__).parents[2]
INPUT_DIR = Path(ROOT_DIR, "./example-input")
OUTPUT_DIR = Path(ROOT_DIR, "./example-output")

TEST_ADMIN_ID = "https://repo.metadatacenter.org/template-instances/d832e5e6-89b9-4d35-a570-15dd15a6792a"


def color_diff(line):
    if line.startswith("+"):
        return Fore.YELLOW + line + Fore.RESET
    elif line.startswith("-"):
        return Fore.RED + line + Fore.RESET
    else:
        return line


def compare_files(file1_path, file2_path):
    with open(file1_path, "r") as file_1:
        file_1_text = file_1.readlines()

    with open(file2_path, "r") as file_2:
        file_2_text = file_2.readlines()

    diff = difflib.unified_diff(
        file_1_text,
        file_2_text,
        fromfile=f"Expected: {file1_path}",
        tofile=f"Actual: {file2_path}",
        n=1,
        lineterm="",
    )
    files_equal = True
    if next(diff, None):
        files_equal = False
        for line in diff:
            print(color_diff(line))
    return files_equal


@pytest.fixture(scope="module")
def setup():
    test_output_path = Path(OUTPUT_DIR, "output-test").mkdir(
        parents=True, exist_ok=True
    )


@pytest.fixture()
def empty_graph():
    graph = Graph()
    graph.bind("dcat", DCAT)
    graph.bind("dcterms", DCTERMS)
    return graph


@patch("cedar.client.CedarClient")
@patch("dcat_exports.cedar_source_data.CedarAdminInstance.get_and_parse_instance")
def test_export_admin_data(get_and_parse_instance, cedar_client, empty_graph, setup):
    # Set Up
    input_file = Path(INPUT_DIR, "test_adm_multiple_creators.json")
    expected_path = Path(OUTPUT_DIR, "test_admin.ttl")
    test_path = Path(OUTPUT_DIR, "output-test", "test_admin.ttl")
    get_and_parse_instance.return_value = empty_graph.parse(
        input_file, format="json-ld", publicID="https://orcid.org"
    )
    admin_instance = CedarAdminInstance(TEST_ADMIN_ID, cedar_client)
    catalog_dict = {
        "description": "Test description",
        "publisher": None,
        "keyword": None,
        "theme": [],
    }
    # Act
    actual = export_admin_data_to_dataset(admin_instance, TEST_ADMIN_ID, catalog_dict)
    # Assert
    actual.to_graph().serialize(destination=test_path)
    assert compare_files(expected_path, test_path)


@freeze_time("2023-06-06")
def test_top_level_bycovid(empty_graph, setup):
    # Set Up
    expected_path = Path(OUTPUT_DIR, "test_root_catalog.ttl")
    test_path = Path(OUTPUT_DIR, "output-test", "test_root_catalog.ttl")
    # Act
    write_top_level(empty_graph)
    empty_graph.serialize(destination=test_path)
    # Assert
    assert compare_files(expected_path, test_path)
