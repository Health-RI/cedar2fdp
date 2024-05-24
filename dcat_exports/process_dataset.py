import re
from datetime import datetime
from enum import Enum
from typing import List, Union

import pandas as pd
from pydantic import ConfigDict
from rdflib import DCAT, DCTERMS, Graph, URIRef
from rdflib.term import BNode, Literal
from sempyro import LiteralField
from sempyro.dcat import DCATDataset
from sempyro.foaf import Agent
from sempyro.time import PeriodOfTime
from sempyro.vcard import VCARD, VCard

from core.logger import get_logger

logger = get_logger()

ADMIN_TEMPLATE_MAPPING = {
    DCTERMS.title: (
        "https://schema.metadatacenter.org/properties/78d03cd1-21ef-41f2-ad99-69bd1118af13",
        "https://schema.metadatacenter.org/properties/9e8b66fb-3f8c-4edc-b2d6-099d398b0bfc",
        "https://schema.metadatacenter.org/properties/a48e48af-7e98-4174-9d1d-5a7b7cf0b788",
        "http://purl.org/dc/elements/1.1/title",
    ),
    DCTERMS.creator: (
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
    DCAT.contactPoint: (
        "https://schema.metadatacenter.org/properties/83257c93-74ba-484b-bae7-8395ca8057a3",
        "https://schema.metadatacenter.org/properties/49cd19d7-5543-4ff5-9861-20e74ce7cfaa",
        "https://schema.metadatacenter.org/properties/ae358774-2e66-40e3-8856-d6d373a180f5",
    ),
    # ("http://purl.org/dc/terms/temporal", "http://purl.org/dc/terms/PeriodOfTime",
    # "http://www.w3.org/ns/dcat#startDate")
    "start": (
        "https://schema.metadatacenter.org/properties/792cb92d-dd83-4b0c-b0ba-6392913c9b09",
        "https://schema.metadatacenter.org/properties/44d6b2d1-24fa-4ee2-85ff-c9bc8565bddc",
        "https://schema.metadatacenter.org/properties/bbca9d8b-a95d-4239-a259-fb40164e5715",
    ),
    # ("http://purl.org/dc/terms/temporal", "http://purl.org/dc/terms/PeriodOfTime",
    # "http://www.w3.org/ns/dcat#endDate")
    "end": (
        "https://schema.metadatacenter.org/properties/792cb92d-dd83-4b0c-b0ba-6392913c9b09",
        "https://schema.metadatacenter.org/properties/44d6b2d1-24fa-4ee2-85ff-c9bc8565bddc",
        "https://schema.metadatacenter.org/properties/e6ba0001-590d-4400-a296-683dee6bf72a",
    ),
    "createdOn": (),
}

# As per documentation https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier
# ORCID iDs are typically the 16-digit identifiers are assigned between 0000-0001-5000-0007 and 0000-0003-5000-0001,
# or between 0009-0000-0000-0000 and 0009-0010-0000-0000. "X" can be at the end.
ORCID_PATTERN = re.compile(
    "^https?:\/\/orcid\.org\/((0000-000(?:1-[5-9]|2-[0-9]|3-[0-4])\d{3}-\d{3}[\dX]?)|(0009-00[0-1](?:[0-9]-[0-9])\d{"
    "3}-\d{3}[\dX]?))"
)

DEFAULT_COVID_THEME = "http://purl.bioontology.org/ontology/ICD10CM/U07.1"


class VCardKind(VCard):
    """
    The vCard class is equivalent to the new Kind class, which is the parent for the four explicit types
    of vCards (Individual, Organization, Location, Group)
    """

    model_config = ConfigDict(
        json_schema_extra={
            "$ontology": "https://www.w3.org/TR/vcard-rdf/",
            "$namespace": str(VCARD),
            "$IRI": VCARD.Kind,
            "$prefix": "v",
        }
    )


class UserTypes(Enum):
    agent = "agent"
    vcard = "vcard"


def user_id_to_vcard_or_agent(
    creator_item, admin_instance_id, orcid_client, return_type: str
):
    return_type = UserTypes(return_type)
    creator_item = str(creator_item).rstrip(",.; ?/\\")
    # To fix entries like https://orcid.org/my-orcid?orcid=000X-XXXX-XXXX-XXXX
    if "?orcid=" in creator_item:
        creator_item = "https://orcid.org/" + creator_item.rsplit("=", maxsplit=1)[-1]
    if not ORCID_PATTERN.fullmatch(creator_item):
        logger.error(
            f"Unexpected creator value: {creator_item}, Admin Template Id: {admin_instance_id}"
        )
    full_name = orcid_client.get_full_name(creator_item)
    if full_name:
        full_name = Literal(full_name)
    else:
        full_name = BNode()
    if return_type == UserTypes.vcard:
        user_object = VCardKind(
            full_name=[LiteralField(value=full_name)], hasUID=URIRef(creator_item)
        )
    elif return_type == UserTypes.agent:
        user_object = Agent(
            name=[LiteralField(value=full_name)], identifier=creator_item
        )
    else:
        raise ValueError(
            f"Incorrect return type {return_type}: `agent` or `vcard` are expected"
        )
    return user_object


def get_user_name_from_cedar(cedar_client, user_id) -> str:
    user_info = cedar_client.get_user_info(user_id)
    return user_info["schema:name"]


def get_creators(
    admin_template, admin_instance_id, cedar_client, orcid_client
) -> List[Agent]:
    try:
        creator_orcid = [
            URIRef(elem["ORCID of Person completing this Form"]["@id"].replace(" ", ""))
            for elem in admin_template["Other"]["ORCID of Person completing this Form"]
        ]
        creator = [
            user_id_to_vcard_or_agent(
                creator_item,
                admin_instance_id,
                orcid_client,
                return_type="agent",
            )
            for creator_item in creator_orcid
            if not isinstance(creator_item, BNode)
        ]
    except (KeyError, AttributeError):
        logger.warning(
            f"No ORCID information provided for {admin_instance_id}, creator will be "
            f"solved based on cedar info"
        )
        cedar_user_id = admin_template["pav:createdBy"]
        creator = [
            Agent(
                name=[
                    LiteralField(
                        value=get_user_name_from_cedar(cedar_client, cedar_user_id)
                    )
                ],
                identifier=cedar_user_id,
            )
        ]
    return creator


def get_publisher(catalog_dict, admin_template, cedar_client) -> List[Agent]:
    publisher = catalog_dict["publisher"]
    if pd.notnull(publisher):
        # publisher_id = [
        #     URIRef(publisher.replace("www.", "http://"))
        #     if publisher.startswith("www.")
        #     else URIRef(publisher)
        # ]
        # todo solve name by link
        publisher = [Agent(name=[publisher], identifier=publisher)]
    else:
        logger.warning(
            f"No publisher information provided for {admin_template['@id']}, it will be "
            f"solved based on cedar info"
        )
        cedar_publisher_id = admin_template["pav:createdBy"]
        publisher = [
            Agent(
                name=[get_user_name_from_cedar(cedar_client, cedar_publisher_id)],
                identifier=cedar_publisher_id,
            )
        ]
    return publisher


def get_contact_points(admin_instance, orcid_client) -> List:
    primary_contact = admin_instance.get_attribute(
        ADMIN_TEMPLATE_MAPPING[DCAT.contactPoint]
    )
    primary_contact = [
        user_id_to_vcard_or_agent(
            contact, admin_instance.admin_instance_id, orcid_client, return_type="vcard"
        )
        for contact in primary_contact
        if not isinstance(contact, BNode)
    ]
    return primary_contact


def export_admin_data_to_dataset(
    admin_instance,
    catalog_dict,
    orcid_client,
    cedar_client,
    fdp_catalog_to_subj_dict,
) -> Union[Graph, None]:

    title = admin_instance.get_title(
        ADMIN_TEMPLATE_MAPPING[DCTERMS.title],
        language_predicate=ADMIN_TEMPLATE_MAPPING["language"][-1],
    )
    if str(title[0]).startswith("TEST-"):
        return None

    admin_template = cedar_client.get_template_instance(
        admin_instance.admin_instance_id
    ).json()

    creator = get_creators(
        admin_template, admin_instance.admin_instance_id, cedar_client, orcid_client
    )

    dates = admin_instance.get_pared_attributes(
        ADMIN_TEMPLATE_MAPPING["start"], ADMIN_TEMPLATE_MAPPING["end"][-1]
    )
    if not dates:
        start_date, end_date = None, None
    else:
        start_date, end_date = dates[0]

    primary_contact = get_contact_points(admin_instance, orcid_client)

    publisher = get_publisher(catalog_dict, admin_template, cedar_client)
    keywords = []
    key_word = catalog_dict["keyword"]
    if key_word and isinstance(key_word, list):
        keywords = [Literal(i) for i in key_word if pd.notnull(i)]
    theme = []
    themes = catalog_dict["theme"]
    if themes and isinstance(key_word, list):
        theme = [URIRef(i) for i in themes if pd.notnull(i)]
    if not theme:
        logger.warning(
            f"No themes for dataset {admin_instance.admin_instance_id}, "
            f"setting to default ('COVID-19', {DEFAULT_COVID_THEME})"
        )
        theme = [URIRef(DEFAULT_COVID_THEME)]

    dataset = DCATDataset(
        title=title,
        creator=creator,
        description=[Literal(catalog_dict["description"])],
        temporal_coverage=[PeriodOfTime(start_date=start_date, end_date=end_date)],
        contact_point=[contact.hasUID for contact in primary_contact],
        publisher=publisher,
        keyword=keywords,
        release_date=datetime.strptime(
            admin_template["pav:createdOn"], "%Y-%m-%dT%H:%M:%S%z"
        ),
        identifier=[admin_instance.admin_instance_id],
        update_date=datetime.strptime(
            admin_template["pav:lastUpdatedOn"], "%Y-%m-%dT%H:%M:%S%z"
        ),
        theme=theme,
        landing_page=[URIRef(catalog_dict["admin_graph_id"])],
    )

    dataset_graph = dataset.to_graph(URIRef(admin_instance.admin_instance_id))
    dataset_graph.add(
        (
            URIRef(admin_instance.admin_instance_id),
            DCTERMS.isPartOf,
            fdp_catalog_to_subj_dict[URIRef(catalog_dict["content_graph_id"])],
        )
    )
    # add contact point node Kind
    for item in primary_contact:
        sbj = URIRef(str(item.hasUID))
        contact = item.to_graph(sbj)
        dataset_graph += contact

    return dataset_graph
