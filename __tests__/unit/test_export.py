import difflib
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from colorama import Fore
from freezegun import freeze_time
from rdflib import DCAT, DCTERMS, RDF, BNode, Graph, Literal, URIRef
from rdflib.compare import to_isomorphic
from requests import Response
from sempyro import LiteralField
from sempyro.dcat import DCATDataset
from sempyro.vcard import VCARD, VCard

from dcat_exports.cedar_source_data import CedarAdminInstance
from dcat_exports.dcat_bycovid_export import (
    build_top_level_catalog,
    export_admin_data_to_dataset,
    write_distributions,
)

ROOT_DIR = Path(__file__).parents[2]
INPUT_DIR = Path(ROOT_DIR, "./example-input")
OUTPUT_DIR = Path(ROOT_DIR, "./example-output")

TEST_ADMIN_ID = URIRef(
    "https://repo.metadatacenter.org/template-instances/d832e5e6-89b9-4d35-a570-15dd15a6792a"
)


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
    Path(OUTPUT_DIR, "output-test").mkdir(parents=True, exist_ok=True)


@pytest.fixture()
def empty_graph():
    graph = Graph()
    graph.bind("dcat", DCAT)
    graph.bind("dcterms", DCTERMS)
    graph.bind("v", VCARD)
    return graph


@pytest.mark.parametrize(
    "user_info_format,file_name",
    [(None, "test_admin.ttl"), (VCARD.VCard, "test_admin_vcard.ttl")],
)
@patch("orcid.orcid_client.OrcidClient")
@patch("cedar.client.CedarClient")
@patch("dcat_exports.cedar_source_data.CedarAdminInstance.get_and_parse_instance")
def test_export_admin_data(
    get_and_parse_instance,
    cedar_client,
    orcid_client,
    empty_graph,
    setup,
    user_info_format,
    file_name,
):
    # Set Up
    orcid_client.get_full_name.side_effect = [
        "Maria de Vries",
        "Jan de Vries",
        "Test_Vorenaam Test_ Achternaam",
        "Next test Value",
    ]
    input_file = Path(INPUT_DIR, "test_adm_multiple_creators.json")
    expected_path = Path(OUTPUT_DIR, file_name)
    test_path = Path(OUTPUT_DIR, "output-test", file_name)
    get_and_parse_instance.return_value = empty_graph.parse(
        input_file, format="json-ld", publicID="https://orcid.org"
    )
    admin_instance = CedarAdminInstance(TEST_ADMIN_ID, cedar_client)
    catalog_dict = {
        "description": "Test description",
        "publisher": None,
        "keyword": None,
        "theme": [],
        "content_graph_id": "https://some-link/catalog",
    }
    mapping = {
        URIRef("https://some-link/catalog"): URIRef("https://example-fdp.com/link1")
    }
    # Act
    actual_graph = export_admin_data_to_dataset(
        admin_instance, TEST_ADMIN_ID, catalog_dict, orcid_client, cedar_client, mapping
    )
    # Assert
    # Compare graphs via isomorphic because diff is not possible with multiple bnodes
    expected = to_isomorphic(Graph().parse(expected_path, format="ttl"))
    actual = to_isomorphic(actual_graph.to_graph(userinfo_format=user_info_format))
    assert actual == expected


@freeze_time("2023-06-06")
def test_top_level_bycovid(empty_graph, setup):
    # Set Up
    expected_path = Path(OUTPUT_DIR, "test_root_catalog.ttl")
    test_path = Path(OUTPUT_DIR, "output-test", "test_root_catalog.ttl")
    # Act
    actual_graph = build_top_level_catalog(
        portal_url=URIRef("https://covid19initiatives.health-ri.nl"),
        fdp_url=URIRef("https://health-ri.sandbox.semlab-leiden.nl"),
    )
    actual_graph.serialize(destination=test_path)
    # Assert
    assert compare_files(expected_path, test_path)


# @pytest.mark.parametrize("test_file_name")
# @patch("cedar.client.CedarClient")
# def test_write_datasets(test_file_name, cedar_client, empty_graph):
#     pass


@pytest.mark.parametrize(
    "user_info,expected_file,info_type",
    [
        (
            [
                {
                    "full_name": Literal("Maria der Vries"),
                    "uid": URIRef("http://orcid.org/test_id1"),
                }
            ],
            "test_vcard_one_user.ttl",
            VCARD.VCard,
        ),
        (
            [
                {
                    "full_name": Literal("Maria der Vries"),
                    "uid": URIRef("http://orcid.org/test_id1"),
                },
                {
                    "full_name": Literal("Jan der Vries"),
                    "uid": URIRef("http://orcid.org/test_id2"),
                },
            ],
            "test_vcard_multiple.ttl",
            VCARD.VCard,
        ),
        (
            [{"full_name": BNode(), "uid": URIRef("http://orcid.org/test_id3")}],
            "test_vcard_no_full_name.ttl",
            VCARD.VCard,
        ),
        ([], "test_vcard_empty_node.ttl", VCARD.VCard),
        ([], "test_vcard_empty_creator_node.ttl", VCARD.VCard),
        (
            [
                {
                    "full_name": Literal("Maria der Vries"),
                    "uid": URIRef("http://orcid.org/test_id1"),
                }
            ],
            "test_vcard_no_type_provided.ttl",
            None,
        ),
        (
            [
                {
                    "full_name": Literal("Maria der Vries"),
                    "uid": URIRef("http://orcid.org/test_id1"),
                }
            ],
            "test_vcard_notVCard_type_provided.ttl",
            DCTERMS.creator,
        ),
    ],
)
def test_add_vcard_info(user_info, info_type, expected_file, empty_graph):
    expected_path = Path(OUTPUT_DIR, expected_file)
    test_path = Path(OUTPUT_DIR, "output-test", expected_file)
    uri = URIRef("http://example.com")
    title = "test title"
    description = "test description"
    creator = [
        VCard(full_name=[LiteralField(value=item.get("full_name"))], hasUID=item["uid"])
        for item in user_info
    ]
    publisher = URIRef("http://example.com")
    contact_point = []
    dcat_instance = DCATDataset(
        title=[title],
        description=[description],
        creator=creator,
        contact_point=contact_point,
        has_version=[URIRef("http://example.com")],
        is_part_of=[URIRef("http://example.com")],
        landing_page=[URIRef("http://example.com/test_project_1")],
        publisher=[publisher],
    )
    # empty_graph.add((uri, RDF.type, DCAT.Dataset))
    # dcat_instance.add_vcard_info(
    #     attribute_name="creator",
    #     graph=empty_graph,
    #     subject=dcat_instance.uri,
    #     predicate=DCTERMS.creator,
    #     userinfo_format=info_type,
    # )
    expected = to_isomorphic(Graph().parse(expected_path))
    actual = to_isomorphic(dcat_instance.to_graph(URIRef("http://example.com")))
    assert actual == expected


@pytest.mark.parametrize(
    "user_info,expected_file,info_type",
    [
        ([], "test_user_uriref_empty_creator_node.ttl", None),
        ([URIRef("http://orcid.org/test_id1")], "test_user_uriref_creator.ttl", None),
    ],
)
def test_user_info_uriref(user_info, info_type, expected_file, empty_graph):
    expected_path = Path(OUTPUT_DIR, expected_file)
    test_path = Path(OUTPUT_DIR, "output-test", expected_file)
    uri = URIRef("http://example.com")
    title = [Literal("test title")]
    description = Literal("test description")
    creator = user_info
    contact_point = []
    publisher = URIRef("http://example.com")
    dcat_instance = DCATDataset(
        uri=uri,
        title=title,
        description=description,
        creator=creator,
        contact_point=contact_point,
        has_version=URIRef("http://example.com"),
        is_part_of=URIRef("http://example.com"),
        landing=URIRef("http://example.com/test_project_1"),
        publisher=publisher,
    )
    empty_graph.add((uri, RDF.type, DCAT.Dataset))
    dcat_instance.add_vcard_info(
        attribute_name="creator",
        graph=empty_graph,
        subject=dcat_instance.uri,
        predicate=DCTERMS.creator,
        userinfo_format=info_type,
    )
    empty_graph.serialize(destination=test_path)
    assert compare_files(expected_path, test_path)


def get_template_by_id(*args, **kwargs):
    result = Response()
    result.code = "OK"
    result.status_code = 200
    templ_id = args[0].split("/")[-1]
    path = Path(INPUT_DIR, f"distr_test{templ_id}.json")
    with open(path, "rb") as t_file:
        template_json_ld = t_file.read()
    result._content = template_json_ld
    result.encoding = "utf-8"
    return result


def add_to_file(*args, **kwargs):
    test_path = Path(OUTPUT_DIR, "output-test", "test_distribution.ttl")
    export_graph = Graph()
    if os.path.exists(test_path):
        export_graph.parse(test_path, format="turtle")
    export_graph += kwargs["metadata"]
    export_graph.serialize(destination=test_path)


@patch("cedar.client.CedarClient")
@patch("fdp.client.FDPClient")
def test_write_distr(fdp_client, client):
    """Tests multiple distributions per project"""
    # Set Up
    expected_path = Path(OUTPUT_DIR, "test_distribution.ttl")
    test_path = Path(OUTPUT_DIR, "output-test", "test_distribution.ttl")
    try:
        os.remove(test_path)
    except OSError:
        pass

    data = {
        "admin_instance_id": [
            "https://example.com/test_id_1",
            "https://example.com/test_id_1",
            "https://example.com/test_id_2",
        ],
        "admin_graph_id": [
            "https://example.com/test_project_1",
            "https://example.com/test_project_1",
            "https://example.com/test_project_2",
        ],
        "catalog_instance_id": [None, None, None],
        "description": [
            "Test description 1",
            "Test description 1",
            "Test description 2",
        ],
        "publisher": [
            "https://example.com/publisher_id_1",
            "https://example.com/publisher_id_1",
            "https://example.com/publisher_id_2",
        ],
        "dataset_id": [
            "https://example.com/dataset_id_1",
            "https://example.com/dataset_id_1",
            "https://example.com/dataset_id_2",
        ],
        "distribution_id": [
            "https://example.com/distr_id_1",
            "https://example.com/distr_id_2",
            "https://example.com/distr_id_3",
        ],
        "content_instance_id": [
            "https://example.com/content_id_1",
            "https://example.com/content_id_1",
            "https://example.com/content_id_2",
        ],
        "keyword": [
            ["national", "hospital care", "COVID-19 phase"],
            ["national", "hospital care", "COVID-19 phase"],
            ["national", "hospital care", "COVID-19 phase"],
        ],
        "focus_area_id": [
            "http://purl.org/zonmw/covid19/10228",
            "http://purl.org/zonmw/covid19/10228",
            "http://purl.org/zonmw/covid19/10228",
        ],
        "focus_area": [
            "care and prevention - organisation of care and prevention",
            "care and prevention - organisation of care and prevention",
            "care and prevention - organisation of care and prevention",
        ],
        "content_title": ["Content title 1", "Content title 1", "Content title 2"],
        "theme": [
            ["http://purl.org/zonmw/covid19/10007"],
            ["http://purl.org/zonmw/covid19/10007"],
            ["http://purl.org/zonmw/covid19/10006"],
        ],
        "count": [0, 0, 0],
        "content_graph_id": [
            URIRef(
                "https://covid19initiatives.health-ri.nl/p/ProjectOverview?focusarea=http://purl.org/zonmw/covid19"
                "/10228"
            ),
            URIRef(
                "https://covid19initiatives.health-ri.nl/p/ProjectOverview?focusarea=http://purl"
                ".org/zonmw/covid19/10228"
            ),
            URIRef(
                "https://covid19initiatives.health-ri.nl/p/ProjectOverview?focusarea=http://purl"
                ".org/zonmw/covid19/10228"
            ),
        ],
    }

    mapping_table = pd.DataFrame.from_dict(data)
    client.get_template_instance.side_effect = get_template_by_id
    mapping = {
        URIRef("https://example.com/test_project_1"): URIRef(
            "https://example.com/fdp_id_test_project_1"
        ),
        URIRef("https://example.com/test_project_2"): URIRef(
            "https://example.com/fdp_id_test_project_2"
        ),
    }
    fdp_client.create_and_publish.side_effect = add_to_file
    write_distributions(
        client,
        mapping_table=mapping_table,
        fdp_dataset_id_to_subj_mapping=mapping,
        fdp_client=fdp_client,
    )
    # Assert
    assert compare_files(expected_path, test_path)
