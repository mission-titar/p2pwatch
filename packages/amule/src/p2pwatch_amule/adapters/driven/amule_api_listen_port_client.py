import http.client
import json
from urllib.error import HTTPError
from urllib.request import OpenerDirector, Request

from p2pwatch_amule.application.ports.driven.listen_port_client import ListenPortClient
from p2pwatch_amule.domain.listen_port_error import ListenPortError

_LOGIN_PATH = "/api/v1/auth/login?include_token=true"
_PREFERENCES_PATH = "/api/v1/preferences"


class AmuleApiListenPortClient(ListenPortClient):
    """Logs in with ``api_password``, then ``PATCH <api_url>/api/v1/preferences`` with both ports,
    by ``url_opener``: a login per call."""

    def __init__(
        self,
        *,
        api_url: str,
        api_password: str,
        timeout_seconds: float,
        url_opener: OpenerDirector,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_password = api_password
        self._timeout_seconds = timeout_seconds
        self._url_opener = url_opener

    def set_listen_port(self, port: int) -> None:
        login_reply = self._send(
            method="POST", path=_LOGIN_PATH, body={"password": self._api_password}, token=None
        )
        try:
            token = json.loads(login_reply).get("token")
        except (ValueError, AttributeError):
            token = None
        if not (isinstance(token, str) and token):
            raise ListenPortError(
                f"amuleapi's login answered without a token ({login_reply[:100]!r})"
            )
        connection = {"tcp_port": port, "udp_port": port}
        self._send(
            method="PATCH", path=_PREFERENCES_PATH, body={"connection": connection}, token=token
        )

    def _send(self, *, method: str, path: str, body: object, token: str | None) -> bytes:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            self._api_url + path, data=json.dumps(body).encode(), headers=headers, method=method
        )
        try:
            with self._url_opener.open(request, timeout=self._timeout_seconds) as response:
                reply: bytes = response.read()
        except HTTPError as error:
            raise ListenPortError(f"{method} {path}: {error.code} {_head(error)!r}") from error
        except (OSError, http.client.HTTPException) as error:
            # URLError and timeouts are OSErrors; a garbled reply is an HTTPException.
            raise ListenPortError(f"{method} {path}: {error}") from error
        return reply


def _head(error: HTTPError) -> bytes:
    """The first 100 bytes of a refusal's body, none when it breaks off."""
    try:
        with error:  # an HTTPError holds the connection open until closed
            return error.read(100)
    except (OSError, http.client.HTTPException):
        return b""
