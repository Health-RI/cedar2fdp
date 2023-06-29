# BYCovid Export

### Version

### v0.1.0

### Source

![](docs/images/Cedar_schema.png)

### Mapping

| Type                      | Health-RI Class | Health-ri Property URI | Source field                                               | Transformation rule/Comment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
|---------------------------|-----------------|------------------------|------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Top-level catalog, portal | Catalog         |                        |                                                            | Portal Project Overview page with base URL from configuration file                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|                           |                 | dcterms:description    |                                                            | Hard-coded to """Health-RI launched the Dutch COVID-19 Data Support Programme to support investigators and health care professionals with tools and services in their search for ways to overcome the pandemic and its' health consequences. ) To facilitate and stimulate an integrated health data infrastructure, Health-RI facilitates investigators by connecting communities, providing data services and tools, and presenting an overview of COVID-19 related initiatives, provided on this site.""" |
|                           |                 | dcterms:issued         |                                                            | Export date in `xsd:date` format                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|                           |                 | dcterms:title          |                                                            | Hard-codded to `COVID-19 related data initiatives - Project overview`                                                                                                                                                                                                                                                                                                                                                                                                                                        |
|                           |                 | dcat:catalog           | `Content Template`.`Scope`.`Focus Area`.`Focus Area`.`@id` | `<Portal Base Link>`.`p/ProjectOverview?focusarea=``<Source field focus area id>`                                                                                                                                                                                                                                                                                                                                                                                                                            |
|                           |                 | dcat:keyword           |                                                            | Hard-codded to `COVID-19`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|                           |                 | foaf:homepage          |                                                            | Portal Project Overview page with base URL from configuration file                                                                                                                                                                                                                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Project level             | Dataset         |                        |                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|                           |                 | dcterms:identifier     |                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|                           |                 | dcterms:description    |                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|                           |                 | dcterms:temporal       |                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|                           |                 |                        |                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |




### Changelog

### v0.1.0

Initial version


[//]: # (<https://covid19initiatives.health-ri.nl/p/Project/27866022694524321> a dcat:Dataset ;)

[//]: # (    dcterms:creator [ a v:VCard ;)

[//]: # (            v:fn "Jutte J.C. de Vries" ;)

[//]: # (            v:hasUID <https://orcid.org/0000-0003-2530-6260> ] ;)

[//]: # (    dcterms:description "COVID-19 breakthrough infections and correlates of protection" ;)

[//]: # (    dcterms:identifier "27866022694524321"^^xsd:token ;)

[//]: # (    dcterms:temporal [ a dcterms:PeriodOfTime ;)

[//]: # (            dcat:endDate "2023-11-30"^^xsd:date ;)

[//]: # (            dcat:startDate "2023-02-01"^^xsd:date ] ;)

[//]: # (    dcterms:title "COVID-19 breakthrough infections and correlates of protection"@en ;)

[//]: # (    dcat:contactPoint [ a v:VCard ;)

[//]: # (            v:fn "Jutte J.C. de Vries" ;)

[//]: # (            v:hasUID <https://orcid.org/0000-0003-2530-6260> ] ;)

[//]: # (    dcat:keyword "Follow-up for detection of SARS-CoV-2 breakthrough infections",)

[//]: # (        "elderly overrepresented",)

[//]: # (        "human disease",)

[//]: # (        "no care setting, healthy at inclusion and followed up",)

[//]: # (        "other",)

[//]: # (        "regional" ;)

[//]: # (    dcat:theme <http://purl.org/zonmw/covid19/10006>,)

[//]: # (        <http://purl.org/zonmw/generic/10006>,)

[//]: # (        <http://purl.org/zonmw/generic/10095> .)
