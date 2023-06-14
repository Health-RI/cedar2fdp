"""Module contains an API client to retrieve data from ORCID"""
from typing import Dict, Union

from rdflib import URIRef
from requests.exceptions import JSONDecodeError

from core.api_client import BasicAPIClient
from core.logger import get_logger

logger = get_logger()


class OrcidClient(BasicAPIClient):
    """ORCID API client class"""

    def __init__(self, token, base_url):
        self.token = token
        headers = self._get_headers()
        super().__init__(base_url, headers)

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def get_orcid_record_info(self, record_id: Union[str, URIRef]) -> Dict:
        """Queries ORCID record by ID or full link, returns response decoded to json dictionary"""
        path = str(record_id)
        if not path.startswith("http"):
            path = f"{self.base_url}/{record_id}"
        response = self.get(path)
        return response.json()

    def get_full_name(self, user_id) -> Union[str, None]:
        """Parses first and last names out of ORC ID record"""
        try:
            orcid_data = self.get_orcid_record_info(user_id)
        except (SystemExit, JSONDecodeError):
            logger.warning(f"User {user_id} not found in ORCID system.")
            return None
        name_data = orcid_data["person"]["name"]
        full_name = None
        if name_data is None:
            logger.warning(
                f"{user_id} name info is not available due to visibility settings"
            )
            return full_name
        # first name is mandatory at registration
        first_name = name_data["given-names"]["value"]
        last_name = name_data["family-name"]
        if last_name:
            last_name = last_name.get("value", "")
        else:
            logger.warning(f"Last name is not provided by user {first_name} {user_id}")
            return first_name
        full_name = f"{first_name} {last_name}"
        return full_name
