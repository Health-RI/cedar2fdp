"""Pydantic models for FDP objects"""
from typing import List

from pydantic import AnyHttpUrl, Field
from rdflib.namespace import DCTERMS
from sempyro import RDFModel
from sempyro.dcat import DCATDataset, DCATDistribution
from sempyro.hri_dcat import HRICatalog

from core.logger import get_logger

logger = get_logger()


class FDPObject(RDFModel):
    is_part_of: List[AnyHttpUrl] = Field(
        description="Link to parent object", rdf_term=DCTERMS.isPartOf, rdf_type="uri"
    )


class FDPCatalog(HRICatalog, FDPObject):
    pass


class FDPDataset(DCATDataset, FDPObject):
    pass


class FDPDistribution(DCATDistribution, FDPObject):
    pass
