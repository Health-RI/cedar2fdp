import requests
from rdflib import Graph


class Client:
    """
    Lightweight FAIR Data Point client.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.token = None

    def login(self, username: str, password: str) -> None:
        r = requests.post(
            f"{self.endpoint}/tokens", json={"email": username, "password": password}
        )
        response = r.json()

        self.token = response["token"]

    def post(self, resource_type: str, metadata: "Graph") -> None:
        hdr = {"Authorization": f"Bearer {self.token}", "Content-Type": "text/turtle"}
        response = requests.post(
            f"{self.endpoint}/{resource_type}", data=metadata.serialize(), headers=hdr
        )

        if response.status_code != 201:
            raise Exception(response.text)
