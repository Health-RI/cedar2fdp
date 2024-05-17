import logging
import re
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Union

import pandas as pd
import yaml
from rdflib import DCAT, DCTERMS, XSD, Graph, URIRef
from rdflib.term import BNode, Literal
from sempyro import LiteralField
from sempyro.foaf import Agent
from sempyro.time import PeriodOfTime
from sempyro.vcard import VCARD, VCard

from cedar.client import CedarClient
from core.logger import get_logger
from covid_portal.covid_portal_client import PortalClient
from dcat_exports.cedar_source_data import CedarAdminInstance
from dcat_exports.export_controller import CedarConfig, ExportController
from fdp.client import FDPClient
from models.bycovid_models import FDPCatalog, FDPDataset, FDPDistribution
from orcid.orcid_client import OrcidClient

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

ZONMW_ONTOLOGY = "http://purl.org/zonmw/covid19"
ZONMW_ONTOLOGY_COVID_FOCUS_AREA_AUTHORS = [
    Agent(name=["Beliën J.A."], identifier="https://orcid.org/0000-0002-7160-5942"),
    Agent(name=["Barbara Magagna"], identifier="https://orcid.org/0000-0003-2195-3997"),
]
HEALTH_RI_URL = URIRef("https://www.health-ri.nl")
DCAT_MEDIATYPE = "https://w3id.org/spar/mediatype"


class ByCovidConfig(metaclass=CedarConfig):
    admin_templ_id = "337cb6f3-eef6-4b2f-9ffb-3f6d6cc9b9ac"
    catalog_templ_id = "2ef5e58f-0770-484d-80ae-23768cc1fda2"
    content_templ_id = "908e33e2-9485-4a93-ab22-1688dc5819dc"
    dataset_templ_id = "de169781-7f75-4aef-a0cb-ac435fe3a4c7"
    distribution_templ_id = "22925909-9fb2-4ac8-a986-6db5ae7049e7"


class PortalEndPoints:
    project = "/p/Project"
    project_overview = f"{project}Overview"
    focus_area_filter = f"{project_overview}?focusarea="


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
        user_object = VCard(
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


def get_user_info_from_cedar(cedar_client, user_id) -> Agent:
    user_info = cedar_client.get_user_info(user_id)
    user_obj = Agent(
        name=[LiteralField(value=user_info["schema:name"])], identifier=user_id
    )
    return user_obj


def export_admin_data_to_dataset(
    admin_instance,
    catalog_dict,
    orcid_client,
    cedar_client,
    fdp_catalog_to_subj_dict,
):
    title = admin_instance.get_title(
        ADMIN_TEMPLATE_MAPPING[DCTERMS.title],
        language_predicate=ADMIN_TEMPLATE_MAPPING["language"][-1],
    )

    creator_orcid = admin_instance.get_attribute(
        ADMIN_TEMPLATE_MAPPING[DCTERMS.creator]
    )

    admin_template = cedar_client.get_template_instance(
        admin_instance.admin_instance_id
    ).json()
    # values with space like "https://orcid.org/ 0000-0002-9614-2577" do not appear in the graph then query from json
    creator = None
    if not creator_orcid or any([isinstance(x, BNode) for x in creator_orcid]):
        try:
            creator_orcid = [
                URIRef(
                    elem["ORCID of Person completing this Form"]["@id"].replace(" ", "")
                )
                for elem in admin_template["Other"][
                    "ORCID of Person completing this Form"
                ]
            ]
        except (KeyError, AttributeError):
            logging.warning(
                f"No ORCID information provided for {admin_instance.admin_instance_id}, creator will be "
                f"solved based on cedar info"
            )
            cedar_user_id = admin_template["pav:createdBy"]
            creator = [get_user_info_from_cedar(cedar_client, cedar_user_id)]
    if creator is None:
        # convert to VCard
        creator = [
            user_id_to_vcard_or_agent(
                creator_item,
                admin_instance.admin_instance_id,
                orcid_client,
                return_type="agent",
            )
            for creator_item in creator_orcid
            if not isinstance(creator_item, BNode)
        ]

    dates = admin_instance.get_pared_attributes(
        ADMIN_TEMPLATE_MAPPING["start"], ADMIN_TEMPLATE_MAPPING["end"][-1]
    )
    if not dates:
        start_date, end_date = None, None
    else:
        start_date, end_date = dates[0]
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

    publisher = catalog_dict["publisher"]
    if pd.notnull(publisher):
        publisher = [
            URIRef(publisher.replace("www.", "http://"))
            if publisher.startswith("www.")
            else URIRef(publisher)
        ]
    elif not any([isinstance(x, BNode) for x in creator_orcid]):
        publisher = creator_orcid
    else:
        publisher = [admin_template["pav:createdBy"]]
    keywords = []
    key_word = catalog_dict["keyword"]
    if key_word and isinstance(key_word, list):
        keywords = [Literal(i) for i in key_word if pd.notnull(i)]
    theme = []
    themes = catalog_dict["theme"]
    if themes and isinstance(key_word, list):
        theme = [URIRef(i) for i in themes if pd.notnull(i)]

    dataset = FDPDataset(
        title=title,
        creator=creator,
        description=[Literal(catalog_dict["description"])],
        temporal_coverage=[PeriodOfTime(start_date=start_date, end_date=end_date)],
        contact_point=primary_contact,
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
        is_part_of=[fdp_catalog_to_subj_dict[URIRef(catalog_dict["content_graph_id"])]],
        landing_page=[URIRef(admin_instance.admin_instance_id)],
    )
    return dataset


def write_datasets(
    client: CedarClient,
    export: Graph,
    map_table: pd.DataFrame,
    orcid_client: OrcidClient,
    fdp_client: FDPClient,
    fdp_catalog_id_to_subj_dict: defaultdict,
) -> defaultdict:
    export.bind("v", VCARD)
    map_table = map_table[
        [
            "admin_instance_id",
            "admin_graph_id",
            "description",
            "publisher",
            "keyword",
            "theme",
            "content_graph_id",
        ]
    ].dropna(subset=["admin_graph_id"], axis="rows")
    admin_ids = map_table["admin_instance_id"].unique()

    fdp_dataset_id_to_subj_dict = defaultdict()
    for admin_instance_id in admin_ids:
        admin_instance = CedarAdminInstance(admin_instance_id, client)

        ds_table = map_table.loc[
            map_table["admin_instance_id"] == admin_instance.admin_instance_id
        ][
            [
                "admin_graph_id",
                "description",
                "publisher",
                "keyword",
                "theme",
                "content_graph_id",
            ]
        ].drop_duplicates(
            subset=["admin_graph_id", "description"]
        )
        ds_list_of_records = ds_table.to_dict("records")
        for record in ds_list_of_records:
            subject = URIRef(admin_instance_id)
            dataset = export_admin_data_to_dataset(
                admin_instance,
                record,
                orcid_client,
                client,
                fdp_catalog_id_to_subj_dict,
            )
            if str(dataset.title).startswith("TEST-"):
                continue
            ds = dataset.to_graph(URIRef(subject))
            # export += dataset.to_graph(userinfo_format=VCARD.VCard)
            try:
                fdp_subject = fdp_client.create_and_publish(
                    resource_type="dataset", metadata=ds
                )
                fdp_dataset_id_to_subj_dict[subject] = fdp_subject
            except SystemExit:
                logger.error(f"Failed to upload dataset {subject}")
    return fdp_dataset_id_to_subj_dict


def build_distribution(
    client: CedarClient, instance_id: URIRef, subject: str, dataset_link: URIRef
) -> Union[Graph, None]:
    """
    Gets required distribution data from Cedar and puts it together ino a distribution rdf graph
    Parameters
    ----------
    client: CedarClient
        API client class instance for Cedar
    instance_id: URIRef
        Cedar instance ID
    subject: subject URI for export
    dataset_link: FDP link of a pre-uploaded dataset
    Returns
    ------
    Graph if no missing data and
    None if a mandatory field is missing
    """
    dist_instance = client.get_template_instance(instance_id).json()
    title = dist_instance["title"]["@value"]
    media_type = dist_instance["distributionMediaType"]
    distribution_format = media_type.get("@id")
    if distribution_format:
        distribution_format = URIRef(distribution_format)
    description = dist_instance["description"]["@value"]
    distribution_license = dist_instance["license"]
    if distribution_license:
        distribution_license = URIRef(distribution_license["@id"])
    else:
        distribution_license = None
    access_url_list = dist_instance["accessURL"]
    if isinstance(access_url_list, list) and access_url_list[0]:
        access_url = [URIRef(x["@id"].strip("/")) for x in access_url_list]
    elif isinstance(access_url_list, str) and access_url_list != "":
        access_url = [URIRef(access_url_list.strip("/"))]
    else:
        logger.error(
            f"Access URL is not provided for the following distribution: {instance_id}"
        )
        return
    distribution = FDPDistribution(
        title=[LiteralField(value=title)],
        description=[LiteralField(value=description)],
        is_part_of=[dataset_link],
        access_url=access_url,
    )
    if distribution_format is not None:
        distribution.media_type = distribution_format
    if distribution_license is not None:
        distribution.license = (distribution_license,)

    return distribution.to_graph(URIRef(subject))


def write_distributions(
    client, mapping_table, fdp_dataset_id_to_subj_mapping, fdp_client
):
    distribution_df = mapping_table.loc[
        pd.notnull(mapping_table["admin_graph_id"])
        & pd.notnull(mapping_table["distribution_id"])
        & (mapping_table["distribution_id"].astype(str) != "")
    ][["admin_graph_id", "distribution_id"]].drop_duplicates()
    distribution_df["count"] = distribution_df.groupby(
        ["admin_graph_id"], dropna=False
    )["distribution_id"].transform("nunique")
    distribution_df["subject"] = distribution_df["admin_graph_id"].apply(
        lambda x: f"{x}-distribution" if "#" in x else f"{x}#distribution"
    )
    distribution_df.loc[(distribution_df["count"].astype(int) > 1), "subject"] = (
        distribution_df["subject"].astype(str)
        + "-"
        + distribution_df.groupby(["admin_graph_id"])["distribution_id"]
        .transform("cumcount")
        .astype(str)
    )
    distr_to_admin = pd.Series(
        distribution_df["subject"].values, index=distribution_df["distribution_id"]
    ).to_dict()
    for instance_id, subject in distr_to_admin.items():
        dataset_link = fdp_dataset_id_to_subj_mapping[
            URIRef(subject.split("distribution")[0].rstrip("#-"))
        ]
        dist_graph = build_distribution(client, instance_id, subject, dataset_link)
        if dist_graph is None:
            continue
        try:
            fdp_client.create_and_publish(
                resource_type="distribution", metadata=dist_graph
            )
        except SystemExit:
            logger.error(f"Failed to upload distribution: {subject}")


def build_top_level_catalog(portal_url: URIRef, fdp_url: URIRef) -> Graph:
    """Adds top-level Catalog pointing to Covid-19 portal"""
    title = "COVID-19 related data initiatives - Project overview"
    description = (
        "Health-RI launched the Dutch COVID-19 Data Support Programme to support investigators and "
        "health care professionals with tools and services in their search for ways to overcome the "
        "pandemic and its' health consequences. \n"
        "To facilitate and stimulate an integrated health data infrastructure, Health-RI facilitates "
        "investigators by connecting communities, providing data services and tools, and presenting an "
        "overview of COVID-19 related initiatives, provided on this site."
    )
    issued = datetime.now().date()
    keywords = [LiteralField(value="COVID-19")]
    homepage = f"{portal_url}{PortalEndPoints.project_overview}"

    catalog = FDPCatalog(
        title=[title],
        description=[description],
        publisher=[HEALTH_RI_URL],
        keyword=keywords,
        is_part_of=[fdp_url],
        release_date=issued,
        landing_page=[homepage],
    )
    export_graph = catalog.to_graph(subject=portal_url)
    return export_graph


def write_catalogs(cedar_export, export_graph, portal_url, fdp_client):
    focus_area_frame = (
        cedar_export.overall_mapping.copy()[
            ["content_graph_id", "focus_area", "focus_area_id"]
        ]
        .dropna()
        .drop_duplicates()
    )

    fdp_url = fdp_client.base_url
    content_items = focus_area_frame.to_dict("records")
    publishers = ZONMW_ONTOLOGY_COVID_FOCUS_AREA_AUTHORS
    sub_links = defaultdict()
    for item in content_items:

        subject = URIRef(item["content_graph_id"])

        title = LiteralField(value=item["focus_area"], datatype=XSD.string)
        description = LiteralField(
            value=f"focus area: {title.value}", datatype=XSD.string
        )

        focus_area_catalog = FDPCatalog(
            title=[title],
            description=[description],
            publisher=publishers,
            is_part_of=[fdp_url],
            themes=[URIRef(item["focus_area_id"])],
            has_version=[URIRef(ZONMW_ONTOLOGY)],
            landing_page=[subject],
        )
        focus_area_graph = focus_area_catalog.to_graph(subject)
        try:
            fdp_subject = fdp_client.create_and_publish(
                resource_type="catalog", metadata=focus_area_graph
            )
            sub_links[subject] = fdp_subject
            export_graph.add((portal_url, DCTERMS.hasPart, fdp_subject))
        except SystemExit:
            logger.error(f"Failed to upload catalog: {subject}")
    try:
        fdp_client.create_and_publish(resource_type="catalog", metadata=export_graph)
    except SystemExit:
        logger.error(f"Failed to upload catalog {portal_url}")
    return sub_links


def get_portal_project_ids(portal_client: PortalClient, portal_url):
    response = portal_client.get_projects_list()
    if response:
        portal_df = pd.DataFrame(data=response.json()["Projects"])[
            ["UniqueId", "CedarAdminTemplateInstanceId"]
        ]
        portal_df["UniqueId"] = f"{portal_url}{PortalEndPoints.project}/" + portal_df[
            "UniqueId"
        ].astype(str)
        portal_df.rename(
            columns={
                "UniqueId": "admin_graph_id",
                "CedarAdminTemplateInstanceId": "admin_instance_id",
            },
            inplace=True,
        )
    else:
        logger.warning(f"No projects found for {portal_url}, please check")
        portal_df = pd.DataFrame(columns=["admin_instance_id", "admin_graph_id"])
    return portal_df


def build_export_graph(
    client, orcid_client, portal_client, portal_url, fdp_url, fdp_client
):
    export_graph = build_top_level_catalog(portal_url, fdp_url)

    cedar_export = ExportController(client, ByCovidConfig)
    cedar_export.overall_mapping = cedar_export.get_catalogs_data()
    cedar_export.merge_datasets_distributions_ids()
    portal_df = get_portal_project_ids(portal_client, portal_url)
    cedar_export.overall_mapping = cedar_export.merge_content_data(portal_df)

    cedar_export.overall_mapping["content_graph_id"] = (
        str(portal_url)
        + PortalEndPoints.focus_area_filter
        + cedar_export.overall_mapping["focus_area_id"].astype(str)
    )
    cedar_export.overall_mapping["content_graph_id"] = cedar_export.overall_mapping[
        "content_graph_id"
    ].apply(URIRef)

    fdp_catalog_id_to_subj_dict = write_catalogs(
        cedar_export=cedar_export,
        export_graph=export_graph,
        portal_url=portal_url,
        fdp_client=fdp_client,
    )

    ds_sub_l = write_datasets(
        client=client,
        export=export_graph,
        map_table=cedar_export.overall_mapping,
        orcid_client=orcid_client,
        fdp_client=fdp_client,
        fdp_catalog_id_to_subj_dict=fdp_catalog_id_to_subj_dict,
    )

    write_distributions(
        client=client,
        mapping_table=cedar_export.overall_mapping,
        fdp_dataset_id_to_subj_mapping=ds_sub_l,
        fdp_client=fdp_client,
    )

    return export_graph


def export_dcat():
    config = yaml.safe_load(open("../config.yml", "r"))
    client = CedarClient(
        api_key=config["cedar"]["apikey"], query_limit=config["cedar"].get("limit")
    )
    orcid = OrcidClient(
        token=config["orcid"]["token"], base_url=config["orcid"]["base_url"]
    )
    portal_url = config["covid_portal"]["base_url"]
    portal_client = PortalClient(
        base_url=f"{portal_url}/rest",
        username=config["covid_portal"]["username"],
        password=config["covid_portal"]["password"],
    )
    fdp_url = URIRef(config["fdp"]["base_url"])

    fdp_client = FDPClient(
        base_url=fdp_url,
        username=config["fdp"]["username"],
        password=config["fdp"]["password"],
    )
    export = build_export_graph(
        client=client,
        orcid_client=orcid,
        portal_client=portal_client,
        portal_url=URIRef(portal_url),
        fdp_url=fdp_url,
        fdp_client=fdp_client,
    )


if __name__ == "__main__":
    export_dcat()
