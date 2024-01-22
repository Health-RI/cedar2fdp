import json
import os
from datetime import datetime
from typing import Optional

import requests
import yaml
from pydantic import BaseModel
from rdflib import DCAT, DCTERMS, FOAF, RDF, XSD, Graph, Literal, URIRef

from fdp.client import FDPClient
from models.bycovid_models import DCATDataSet, DCATDistribution

MSK_URL = URIRef("https://www.mskcc.org")
HRI_URL = URIRef("https://www.health-ri.nl")

UMLS_BASE = "https://ncim.nci.nih.gov/ncimbrowser/ConceptReport.jsp?code="
NCI_BASE = "https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code="

PUBMED_BASE = "https://pubmed.ncbi.nlm.nih.gov"

instances = {
    "cBioPortal Health-RI": "https://cbioportal.health-ri.nl",
    # "cBioPortal": "https://cbioportal.org"
}


class VCard(BaseModel):
    full_name: Optional[Literal]
    uid: URIRef


def get_studies(base_link):
    if base_link == "https://cbioportal.health-ri.nl":
        with open("./temp_cbio_data/studies.json", "r") as file:
            studies = json.load(file)
    else:
        link = f"{base_link}/api/studies"
        studies = requests.get(link).json()
    return studies


def get_cancer_type_info(cancer_type):
    if "-" in cancer_type:
        cancer_type = cancer_type.split("-")[0]
    keywords = []
    theme = []
    url = f"https://oncotree.mskcc.org:443/api/tumorTypes/search/code/{cancer_type}"
    info = requests.get(url).json()
    if info:
        info = info[0]
        name = info.get("name")
        main_type = info.get("mainType")
        refs = info["externalReferences"]
        tissue = info.get("tissue")
        keywords += [Literal(name), Literal(main_type), Literal(tissue)]
        if refs:
            umls = refs.get("UMLS")
            if umls:
                theme.append(URIRef(f"{UMLS_BASE}{umls[0]}"))
            nci = refs.get("NCI")
            if nci:
                theme.append(URIRef(f"{NCI_BASE}{nci[0]}"))
    return keywords, theme


def create_study(study_json, base_link, catalog_id):
    study_id = study_json["studyId"]
    study_url = URIRef(f"{base_link}/study/summary?id={study_id}")
    title = study_json["name"]
    description = study_json["description"]
    contact_point = []
    cancer_type = study_json["cancerTypeId"]
    published = Literal(study_json["importDate"])
    keywords, theme = get_cancer_type_info(cancer_type)
    tags_path = f"./temp_cbio_data/{study_id}_tags.json"
    if os.path.exists(tags_path):
        with open(tags_path, "r") as tags_file:
            tags = json.load(tags_file)
            analyst = tags.get("Analyst")
            if analyst:
                user = VCard(
                    full_name=Literal(analyst["name"]), uid=URIRef(analyst["email"])
                )
                contact_point.append(user)
    if base_link == "https://cbioportal.health-ri.nl":
        publisher = [URIRef(HRI_URL)]
    else:
        publisher = [URIRef(MSK_URL)]
    references = [URIRef(f"{PUBMED_BASE}/{x}") for x in study_json["pmid"].split(",")]

    study = DCATDataSet(
        uri=study_url,
        title=[Literal(title)],
        description=Literal(description),
        creator=contact_point,
        contact_point=contact_point,
        publisher=publisher,
        keyword=keywords,
        theme=theme,
        is_part_of=URIRef(catalog_id),
        is_referenced_by=references,
        issued=published,
        modified=published,
        # has_version=study_url,
        landing=study_url,
    )
    study = study.to_graph()
    return study


def add_distributions(instance_base, fdp_client, dataset_id, study_json):
    study_id = study_json["studyId"]
    clinical_url = URIRef(f"{instance_base}/study/clinicalData?id={study_id}")
    summary_url = URIRef(f"{instance_base}/study/summary?id={study_id}")
    api_url = f"{instance_base}/api/molecular_profile"
    clinical = DCATDistribution(
        uri=clinical_url,
        title=Literal(f"Clinical data for {study_json['name']}"),
        description=Literal(f"Clinical data for {study_json['name']}"),
        distr_format=URIRef(
            "https://www.iana.org/assignments/media-types/media-types.xhtml#text"
        ),
        is_part_of=dataset_id,
        access_url=[clinical_url],
    ).to_graph()
    fdp_client.create_and_publish(resource_type="distribution", metadata=clinical)

    with open("./temp_cbio_data/molecular_profiles.json", "r") as mp_file:
        mol_profiles = json.load(mp_file)
    mol_profiles = [mp for mp in mol_profiles if mp["studyId"] == study_id]
    for mol_profile in mol_profiles:
        mp_graph = DCATDistribution(
            uri=URIRef(f"{api_url}/{mol_profile['molecularProfileId']}"),
            title=Literal(mol_profile["name"]),
            description=Literal(
                f"{mol_profile['description']} ({mol_profile['datatype']})"
            ),
            distr_format=URIRef(
                "https://www.iana.org/assignments/media-types/" "media-types.xhtml#text"
            ),
            is_part_of=dataset_id,
            access_url=[summary_url],
        ).to_graph()
        fdp_client.create_and_publish(resource_type="distribution", metadata=mp_graph)


def import_cbio(export_graph, fdp_client, instance_name, instance_link):
    if instance_name == "cBioPortal Health-RI":
        publisher = HRI_URL
    else:
        publisher = MSK_URL
    cbio_catalog = create_catalog(
        export_graph=export_graph,
        fdp_url=fdp_client.base_url,
        instance_name=instance_name,
        instance_link=instance_link,
        publisher=publisher,
    )
    # catalog_id = URIRef("https://health-ri.sandbox.semlab-leiden.nl/catalog/5c85cb9f-be4a-406c-ab0a-287fa787caa0")
    catalog_id = fdp_client.create_and_publish(
        resource_type="catalog", metadata=cbio_catalog
    )
    studies = get_studies(instance_link)
    for study in studies:
        study_graph = create_study(study, instance_link, catalog_id)
        dataset_id = fdp_client.create_and_publish(
            resource_type="dataset", metadata=study_graph
        )
        add_distributions(instance_link, fdp_client, dataset_id, study)


def create_catalog(
    export_graph, fdp_url, instance_name, instance_link, publisher
) -> Graph:
    portal_url = URIRef(instance_link)
    description = "cBioPortal for Cancer genomics"
    issued = datetime.now().date()
    keywords = ["cancer", "genomics"]
    homepage = portal_url
    export_graph.bind("foaf", FOAF)
    export_graph.add((portal_url, RDF.type, DCAT.Catalog))
    export_graph.add((portal_url, DCTERMS.title, Literal(instance_name)))
    export_graph.add((portal_url, DCTERMS.description, Literal(description)))
    export_graph.add((portal_url, DCTERMS.issued, Literal(issued, datatype=XSD.date)))
    export_graph.add((portal_url, DCTERMS.isPartOf, fdp_url))
    export_graph.add((portal_url, DCTERMS.publisher, publisher))
    for keyword in keywords:
        export_graph.add((portal_url, DCAT.keyword, Literal(keyword)))
    export_graph.add((portal_url, FOAF.homepage, URIRef(homepage)))
    return export_graph


if __name__ == "__main__":
    config = yaml.safe_load(open("../../config.yml", "r"))

    fdp_url = URIRef(config["fdp"]["base_url"])

    fdp_client = FDPClient(
        base_url=fdp_url,
        username=config["fdp"]["username"],
        password=config["fdp"]["password"],
    )
    export_graph = Graph()
    fdp_url = URIRef("https://health-ri.sandbox.semlab-leiden.nl")
    for key, value in instances.items():
        import_cbio(export_graph, fdp_client, key, value)
