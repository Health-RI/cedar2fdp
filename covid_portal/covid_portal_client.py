"""Module contains a REST API client for COVID-19 portal"""
import base64
from typing import Union

from core.api_client import BasicAPIClient


class PortalClient(BasicAPIClient):
    """Client for COVID-19 portal API"""

    def __init__(self, base_url: str, username: str, password: str):
        self.username = username
        self.password = password
        headers = self._get_headers()
        super().__init__(base_url, headers)

    def _generate_token(self):
        return base64.b64encode(
            f"{self.username}:{self.password}".encode("ascii")
        ).decode("ascii")

    def _get_headers(self):
        return {
            "Authorization": f"Basic {self._generate_token()}",
            "Accept": "application/json",
        }

    def get_projects_list(self):
        """Gets list of projects from portal"""
        path = f"{self.base_url}/project/v1/ProjectInformation/ProjectList"
        response = self.get(path=path)
        return response

    def get_project_by_id(self, project_id: Union[int, str]):
        """Gets project information from portal by project id"""
        path = f"{self.base_url}/project/v1/ProjectInformation/Project"
        params = {"UniqueId": str(project_id)}
        response = self.get(path=path, params=params)
        return response
