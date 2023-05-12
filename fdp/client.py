import requests
from rdflib import Graph

from core.api_client import BasicAPIClient


class FDPClient(BasicAPIClient):
    """Client for FAIR Data Point client"""

    def __init__(self, base_url: str, username: str, password: str):
        self.username = username
        self.password = password
        self.token = self.login_fdp(base_url)
        headers = self.get_headers()
        super().__init__(base_url, headers)

    def login_fdp(self, base_url: str) -> str:
        token_response = requests.post(
            f"{base_url}/tokens",
            json={"email": self.username, "password": self.password},
        )
        token_response.raise_for_status()
        response = token_response.json()
        return response["token"]

    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "text/turtle"}

    def post_serialised(self, resource_type: str, metadata: "Graph") -> None:
        path = f"{self.base_url}/{resource_type}"
        response = self.post(path=path, data=metadata.serialize())
