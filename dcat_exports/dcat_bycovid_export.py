from collections import defaultdict
from datetime import datetime
from typing import Union

import pandas as pd
import yaml
from pydantic import Field
from rdflib import DCAT, DCTERMS, XSD, Graph, URIRef
from sempyro import LiteralField
from sempyro.dcat import DCATDistribution
from sempyro.foaf import Agent
from sempyro.hri_dcat import HRICatalog
from sempyro.vcard import VCARD

from cedar.client import CedarClient
from core.logger import get_logger
from covid_portal.covid_portal_client import PortalClient
from dcat_exports.cedar_source_data import CedarAdminInstance
from dcat_exports.export_controller import CedarConfig, ExportController
from dcat_exports.process_dataset import export_admin_data_to_dataset
from fdp.client import FDPClient
from orcid.orcid_client import OrcidClient

logger = get_logger()


ZONMW_ONTOLOGY = "http://purl.org/zonmw/covid19"
ZONMW_ONTOLOGY_COVID_FOCUS_AREA_AUTHORS = [
    Agent(name=["Beliën J.A."], identifier="https://orcid.org/0000-0002-7160-5942"),
    Agent(name=["Barbara Magagna"], identifier="https://orcid.org/0000-0003-2195-3997"),
]
HEALTH_RI_URL = "https://www.health-ri.nl"
DCAT_MEDIATYPE = "https://w3id.org/spar/mediatype"
DEFAULT_MEDIATYPE = "https://w3id.org/spar/mediatype/text/csv.html"


class FDPDistribution(DCATDistribution):
    """
    # todo either replace it with DCATDistribution or HRIDistribution or update SemPyRO if mediaType is a string
    Distribution class with mediaType field as a string
    """

    media_type: str = Field(
        description="The media type of the distribution as defined by IANA",
        rdf_term=DCAT.mediaType,
        rdf_type="xsd:string",
    )


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
            dataset_graph = export_admin_data_to_dataset(
                admin_instance,
                record,
                orcid_client,
                client,
                fdp_catalog_id_to_subj_dict,
            )
            if dataset_graph is None:
                continue
            try:
                fdp_subject = fdp_client.create_and_publish(
                    resource_type="dataset", metadata=dataset_graph
                )
                fdp_dataset_id_to_subj_dict[admin_instance_id] = fdp_subject
            except (SystemExit, UnicodeEncodeError, KeyError) as e:
                logger.error(
                    f"Failed to upload dataset {admin_instance_id} due to the following error: \n{e}"
                )
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
    if not distribution_format:
        # if distribution_format:
        # distribution_format = URIRef(distribution_format)
        # else:
        distribution_format = dist_instance["distributionFormat"].get("@value")
        if distribution_format and not distribution_format.startswith("http"):
            distribution_format = f"{DCAT_MEDIATYPE}/text#{distribution_format}"
    if not distribution_format:
        logger.warning(
            f"No mediatype specified for distribution {subject}, setting to default {DEFAULT_MEDIATYPE}"
        )
        distribution_format = DEFAULT_MEDIATYPE
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
        media_type=distribution_format,
        access_url=access_url,
    )

    if distribution_license is not None:
        distribution.license = distribution_license

    distribution_graph = distribution.to_graph(URIRef(subject))
    distribution_graph.add((URIRef(subject), DCTERMS.isPartOf, URIRef(dataset_link)))

    return distribution_graph


def write_distributions(
    client, mapping_table, fdp_dataset_id_to_subj_mapping, fdp_client
):
    logger.info("Distributions")
    distribution_df = mapping_table.loc[
        pd.notnull(mapping_table["admin_instance_id"])
        & pd.notnull(mapping_table["distribution_id"])
        & (mapping_table["distribution_id"].astype(str) != "")
    ][["admin_instance_id", "distribution_id"]].drop_duplicates()
    distr_to_admin = pd.Series(
        distribution_df["admin_instance_id"].values,
        index=distribution_df["distribution_id"],
    ).to_dict()
    for instance_id, admin_id in distr_to_admin.items():
        dataset_link = fdp_dataset_id_to_subj_mapping.get(admin_id)
        if dataset_link:
            dist_graph = build_distribution(
                client, instance_id, instance_id, dataset_link
            )
            if dist_graph is None:
                continue
            try:
                fdp_client.create_and_publish(
                    resource_type="distribution", metadata=dist_graph
                )
            except SystemExit:
                logger.error(f"Failed to upload distribution: {instance_id}")
        else:
            logger.warning(
                f"Dataset {admin_id} was not uploaded to FDP,"
                f"skipping corresponding distribution {instance_id}"
            )


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
    publisher = Agent(name=["Health-RI"], identifier=HEALTH_RI_URL)

    catalog = HRICatalog(
        title=[title],
        description=[description],
        publisher=[publisher],
        keyword=keywords,
        release_date=issued,
        landing_page=[homepage],
    )
    export_graph = catalog.to_graph(subject=portal_url)
    export_graph.add((portal_url, DCTERMS.isPartOf, fdp_url))
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

        focus_area_catalog = HRICatalog(
            title=[title],
            description=[description],
            publisher=publishers,
            themes=[URIRef(item["focus_area_id"])],
            has_version=[URIRef(ZONMW_ONTOLOGY)],
            landing_page=[subject],
        )
        focus_area_graph = focus_area_catalog.to_graph(subject)
        focus_area_graph.add((subject, DCTERMS.isPartOf, fdp_url))
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
