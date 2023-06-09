from pathlib import Path
from unittest.mock import patch

from rdflib import XSD, BNode, Graph, Literal, URIRef

from dcat_exports.export_utils import implement_recursion, update_language

ROOT_DIR = Path(__file__).parents[2]
INPUT_DIR = Path(ROOT_DIR, "./example-input")
# OUTPUT_DIR = Path(ROOT_DIR, "./example-output")

# Not importing mapping here to test utility functions independently
ADMIN_TEMPLATE_MAPPING = {
    "title": (
        "https://schema.metadatacenter.org/properties/78d03cd1-21ef-41f2-ad99-69bd1118af13",
        "https://schema.metadatacenter.org/properties/9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc",
        "https://schema.metadatacenter.org/properties/a48e48af-7e98-4174-9d1d-5a7b7cf0b788",
        "http://purl.org/dc/elements/1.1/title",
    ),
    "creator": (
        "https://schema.metadatacenter.org/properties/e7f6696a-4e6b-491f-9429-23037579452e",
        "https://schema.metadatacenter.org/properties/6455acbe-f02d-4628-8748-b3e98649076c",
        "https://schema.metadatacenter.org/properties/fe7e40b0-8c55-4221-bc82-399e80d19846",
    ),
    "language": (
        "https://schema.metadatacenter.org/properties/78d03cd1-21ef-41f2-ad99-69bd1118af13",
        "https://schema.metadatacenter.org/properties/9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc",
        "https://schema.metadatacenter.org/properties/a48e48af-7e98-4174-9d1d-5a7b7cf0b788",
        "http://def.isotc211.org/iso19115/2003/IdentificationInformation#MD_DataIdentification.language",
    ),
    "start": (
        "https://schema.metadatacenter.org/properties/792cb92d-dd83-4b0c-b0ba-6392913c9b09",
        "https://schema.metadatacenter.org/properties/44d6b2d1-24fa-4ee2-85ff-c9bc8565bddc",
        "https://schema.metadatacenter.org/properties/bbca9d8b-a95d-4239-a259-fb40164e5715",
    ),
    "end": (
        "https://schema.metadatacenter.org/properties/792cb92d-dd83-4b0c-b0ba-6392913c9b09",
        "https://schema.metadatacenter.org/properties/44d6b2d1-24fa-4ee2-85ff-c9bc8565bddc",
        "https://schema.metadatacenter.org/properties/e6ba0001-590d-4400-a296-683dee6bf72a",
    ),
}

TEST_ADMIN_ID = "https://repo.metadatacenter.org/template-instances/d832e5e6-89b9-4d35-a570-15dd15a6792a"


def test_recursion_gets_values():
    input_file = Path(INPUT_DIR, "test_adm_single_creator.json")
    graph_data = Graph().parse(
        input_file, format="json-ld", publicID="https://orcid.org"
    )
    expected = [(URIRef("https://orcid.org/0000-0001-5878-7481"), None)]
    obj_list = []
    creator = implement_recursion(
        ADMIN_TEMPLATE_MAPPING["creator"],
        URIRef(TEST_ADMIN_ID),
        graph_data,
        obj_list,
    )
    assert expected == creator


def test_recursion_gets_multiple_values():
    input_file = Path(INPUT_DIR, "test_adm_multiple_creators.json")
    graph_data = Graph().parse(
        input_file, format="json-ld", publicID="https://orcid.org"
    )
    expected = [
        (URIRef("https://orcid.org/0000-0001-5878-7481"), None),
        (URIRef("https://orcid.org/0000-0001-5878-7481_test"), None),
        (URIRef("https://orcid.org/0000-0001-5878-7481_test2"), None),
    ]
    obj_list = []
    creator = implement_recursion(
        ADMIN_TEMPLATE_MAPPING["creator"],
        URIRef(TEST_ADMIN_ID),
        graph_data,
        obj_list,
    )
    assert expected == creator


def test_recursion_diverged_values():
    input_file = Path(INPUT_DIR, "test_adm_multiple_creators.json")
    graph_data = Graph().parse(input_file, format="json-ld")
    expected = [
        (
            Literal("2023-05-01", datatype=XSD.date),
            Literal("2023-06-01", datatype=XSD.date),
        )
    ]
    obj_list = []
    dates = implement_recursion(
        ADMIN_TEMPLATE_MAPPING["start"],
        URIRef(TEST_ADMIN_ID),
        graph_data,
        obj_list,
        ADMIN_TEMPLATE_MAPPING["end"][-1],
    )
    assert expected == dates


def test_recursion_languages_single():
    input_file = Path(INPUT_DIR, "test_adm_single_language.json")
    graph_data = Graph().parse(input_file, format="json-ld")
    expected = [
        (
            Literal("TEST-dummy test admin template"),
            URIRef(
                "https://www.omg.org/spec/LCC/Languages/LaISO639-1-LanguageCodes/en"
            ),
        )
    ]
    obj_list = []
    title = implement_recursion(
        ADMIN_TEMPLATE_MAPPING["title"],
        URIRef(TEST_ADMIN_ID),
        graph_data,
        obj_list,
        ADMIN_TEMPLATE_MAPPING["language"][-1],
    )
    assert expected == title


def test_recursion_multiple_related():
    input_file = Path(INPUT_DIR, "test_adm_multiple_creators.json")
    graph_data = Graph().parse(input_file, format="json-ld")
    expected = [
        (
            Literal("TEST-dummy test admin template"),
            URIRef(
                "https://www.omg.org/spec/LCC/Languages/LaISO639-1-LanguageCodes/en"
            ),
        ),
        (
            Literal("TEST-andere test naam"),
            URIRef(
                "https://www.omg.org/spec/LCC/Languages/LaISO639-1-LanguageCodes/nl"
            ),
        ),
    ]
    obj_list = []
    title = implement_recursion(
        ADMIN_TEMPLATE_MAPPING["title"],
        URIRef(TEST_ADMIN_ID),
        graph_data,
        obj_list,
        ADMIN_TEMPLATE_MAPPING["language"][-1],
    )
    assert expected == title


def test_upd_language():
    title = (
        Literal("TEST-dummy test admin template"),
        URIRef("https://www.omg.org/spec/LCC/Languages/LaISO639-1-LanguageCodes/en"),
    )
    expected = Literal("TEST-dummy test admin template", lang="en")
    actual = update_language(title)
    assert expected == actual


@patch("logging.Logger.warning")
def test_unexpected_language(mock_logger):
    # mock_logger = MagicMock()
    title = (
        Literal("TEST-dummy test admin template"),
        URIRef("https://www.omg.org/spec/LCC/Languages/LaISO639-1-LanguageCodes/uk"),
    )
    update_language(title, TEST_ADMIN_ID)
    mock_logger.assert_called_once_with(
        f'Unexpected language "uk" for title '
        f'"TEST-dummy test admin template", cedar ID {TEST_ADMIN_ID}, please check'
    )


@patch("logging.Logger.warning")
def test_no_language(mock_logger):
    # mock_logger = MagicMock()
    title = (Literal("TEST-dummy test admin template"), BNode())
    update_language(title, TEST_ADMIN_ID)
    mock_logger.assert_called_once_with(
        f"No relevant language provided for value "
        f'"TEST-dummy test admin template", cedar ID {TEST_ADMIN_ID}'
    )
