from typing import Union
from urllib.parse import urlparse

import requests
from rdflib import Graph, URIRef

from core.api_client import BasicAPIClient


class FDPEndPoints:
    meta = "meta"
    state = f"{meta}/state"
    members = "members"
    expanded = "expanded"


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

    def _update_session_headers(self):
        self.session.headers.update(self.headers)

    def _change_content_type(self, content_type):
        self.headers["Content-Type"] = content_type
        self._update_session_headers()

    def post_serialised(
        self, resource_type: str, metadata: "Graph"
    ) -> Union[requests.Response, None]:
        self._change_content_type("text/turtle")
        path = f"{self.base_url}/{resource_type}"
        response = self.post(path=path, data=metadata.serialize())
        return response

    def get_data(self, path: str) -> requests.Response:
        response = self.get(path=path)
        return response

    def delete_record(self, path: str) -> requests.Response:
        response = self.delete(path=path)
        return response

    def publish_record(self, record_url):
        self._change_content_type("application/json")
        path = f"{record_url}/{FDPEndPoints.state}"
        data = '{"current": "PUBLISHED"}'
        self.update(path=path, data=data)

    def create_and_publish(self, resource_type: str, metadata: "Graph") -> URIRef:
        post_response = self.post_serialised(
            resource_type=resource_type, metadata=metadata
        )
        fdp_subject = next(Graph().parse(data=post_response.text).subjects())
        fdp_path = urlparse(fdp_subject).path
        if fdp_path.count("/") > 2:
            fdp_path = fdp_path.rsplit("/", maxsplit=2)[0]
        fdp_subject = URIRef(f"{self.base_url}{fdp_path}")
        self.publish_record(fdp_subject)
        return fdp_subject
