import encodings
import logging
import sys
from typing import Dict
from urllib.parse import urljoin

import requests
import urllib3
from requests import Response

logger = logging.getLogger(__name__)


class BasicAPIClient:
    """Basic class for API client"""

    def __init__(self, base_url, headers):
        self.base_url = base_url
        self.headers = headers
        self.session = requests.session()
        self.session.headers.update(self.headers)
        self.ssl_verification = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _call_method(self, method, path, params: Dict = None, data=None):
        if method.upper() not in ["GET", "POST", "PUT", "DELETE"]:
            raise ValueError(f"Unsupported method {method}")
        url = urljoin(self.base_url, path)
        response = None
        try:
            response = self.session.request(
                method, url, params=params, data=data, verify=self.ssl_verification
            )
            response.raise_for_status()
            response.encoding = encodings.utf_8.getregentry().name
            return response
        except requests.exceptions.HTTPError as e:
            logger.error(e)
            if response is not None:
                logger.error(response.text)
            sys.exit(1)
        except requests.exceptions.ConnectionError as e:
            logger.error(e)
            sys.exit(1)
        except requests.exceptions.Timeout as e:
            logger.error(e)
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            logger.error(e)
            sys.exit(1)

    def get(self, path: str, params: Dict = None) -> Response:
        return self._call_method("GET", path, params=params)

    def post(self, path: str, params: Dict = None, data=None) -> Response:
        return self._call_method("POST", path, params=params, data=data)

    def update(self, path: str, params: Dict = None, data=None) -> Response:
        return self._call_method("PUT", path, params=params, data=data)

    def delete(self, path: str, params: Dict = None, data=None) -> Response:
        return self._call_method("DELETE", path, params=params, data=data)
