import codecs
from typing import Union

import requests
from rdflib import Graph, URIRef

from core.api_client import BasicAPIClient

latin_dict = {
    ord("¡"): "!",
    ord("¢"): "c",
    ord("£"): "L",
    ord("¤"): "o",
    ord("¥"): "Y",
    ord("¦"): "|",
    ord("§"): "S",
    ord("¨"): "`",
    ord("©"): "c",
    ord("ª"): "a",
    ord("«"): "<<",
    ord("¬"): "-",
    ord("­"): "-",
    ord("®"): "R",
    ord("¯"): "-",
    ord("–"): "-",
    ord("°"): "o",
    ord("±"): "+-",
    ord("²"): "2",
    ord("³"): "3",
    ord("´"): "'",
    ord("µ"): "u",
    ord("¶"): "P",
    ord("·"): ".",
    ord("¸"): ",",
    ord("¹"): "1",
    ord("º"): "o",
    ord("»"): ">>",
    ord("¼"): "1/4",
    ord("½"): "1/2",
    ord("¾"): "3/4",
    ord("¿"): "?",
    ord("À"): "A",
    ord("Á"): "A",
    ord("Â"): "A",
    ord("Ã"): "A",
    ord("Ä"): "A",
    ord("Å"): "A",
    ord("Æ"): "Ae",
    ord("Ç"): "C",
    ord("È"): "E",
    ord("É"): "E",
    ord("Ê"): "E",
    ord("Ë"): "E",
    ord("Ì"): "I",
    ord("Í"): "I",
    ord("Î"): "I",
    ord("Ï"): "I",
    ord("Ð"): "D",
    ord("Ñ"): "N",
    ord("Ò"): "O",
    ord("Ó"): "O",
    ord("Ô"): "O",
    ord("Õ"): "O",
    ord("Ö"): "O",
    ord("×"): "*",
    ord("Ø"): "O",
    ord("Ù"): "U",
    ord("Ú"): "U",
    ord("Û"): "U",
    ord("Ü"): "U",
    ord("Ý"): "Y",
    ord("Þ"): "p",
    ord("ß"): "b",
    ord("à"): "a",
    ord("á"): "a",
    ord("â"): "a",
    ord("ã"): "a",
    ord("ä"): "a",
    ord("å"): "a",
    ord("æ"): "ae",
    ord("ç"): "c",
    ord("è"): "e",
    ord("é"): "e",
    ord("ê"): "e",
    ord("ë"): "e",
    ord("ì"): "i",
    ord("í"): "i",
    ord("î"): "i",
    ord("ï"): "i",
    ord("ð"): "d",
    ord("ñ"): "n",
    ord("ò"): "o",
    ord("ó"): "o",
    ord("ô"): "o",
    ord("õ"): "o",
    ord("ö"): "o",
    ord("÷"): "/",
    ord("ø"): "o",
    ord("ù"): "u",
    ord("ú"): "u",
    ord("û"): "u",
    ord("ü"): "u",
    ord("ý"): "y",
    ord("þ"): "p",
    ord("ÿ"): "y",
    ord("’"): "'",
    ord("‘"): "'",
    ord("”"): "''",
    ord("“"): "''",
}


def latin2ascii(error):
    return latin_dict.get(ord(error.object[error.start]), "?"), error.end


def serialize_and_decode(metadata: "Graph") -> bytes:
    """
    Serializes graph data and replaces unicode characters FDP can not ingest to prevent
    400 Bad request: can't parse RDF error
    Characters are replaces with the closest option or a question mark
    """
    codecs.register_error("latin2ascii", latin2ascii)
    data = metadata.serialize().encode("ascii", "latin2ascii")
    return data


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
        data = serialize_and_decode(metadata=metadata)
        response = self.post(path=path, data=data)
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
        fdp_subject = URIRef(post_response.headers["Location"])
        self.publish_record(fdp_subject)
        return fdp_subject
