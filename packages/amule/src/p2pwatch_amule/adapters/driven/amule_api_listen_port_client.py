import http.client
import json
from http import HTTPStatus
from urllib.error import HTTPError, URLError
from urllib.request import OpenerDirector, Request

from p2pwatch_amule.application.ports.driven.listen_port_client import ListenPortClient
from p2pwatch_amule.domain.listen_port_error import (
    ApiNotReadyError,
    ListenPortError,
    ListenPortRejectedError,
)

_LOGIN_PATH = "/api/v1/auth/login?include_token=true"
_PREFERENCES_PATH = "/api/v1/preferences"


class AmuleApiListenPortClient(ListenPortClient):
    """``GET`` and ``PATCH <api_url>/api/v1/preferences`` by ``url_opener``, under a token kept from
    a login with ``api_password``, logged in again once when amuleapi refuses it."""

    def __init__(
        self,
        *,
        api_url: str,
        api_password: str,
        timeout_seconds: float,
        url_opener: OpenerDirector,
    ) -> None:
        self._api_url = api_url
        self._api_password = api_password
        self._timeout_seconds = timeout_seconds
        self._url_opener = url_opener
        self._token: str | None = None

    def read_listen_port(self) -> int:
        status, reply = self._send_with_token(method="GET", body=None)
        message = f"GET {_PREFERENCES_PATH}: {status} {reply!r}"
        if status == HTTPStatus.UNAUTHORIZED:
            raise ApiNotReadyError(message)
        _raise_unless_success(status=status, message=message)
        try:
            tcp_port = json.loads(reply)["connection"]["tcp_port"]
        except (ValueError, LookupError, TypeError):
            tcp_port = None
        if type(tcp_port) is not int:  # a JSON true is a Python int too
            raise ListenPortError(
                f"amuleapi's preferences answered without a TCP port ({reply[:100]!r})"
            )
        return tcp_port

    def set_listen_port(self, port: int) -> None:
        connection = {"tcp_port": port, "udp_port": port}
        status, reply = self._send_with_token(method="PATCH", body={"connection": connection})
        message = f"PATCH {_PREFERENCES_PATH}: {status} {reply!r}"
        if status == HTTPStatus.BAD_REQUEST:
            raise ListenPortRejectedError(message)
        if status == HTTPStatus.UNAUTHORIZED:
            raise ApiNotReadyError(message)
        _raise_unless_success(status=status, message=message)

    def _send_with_token(self, *, method: str, body: object) -> tuple[int, bytes]:
        """The preferences under the kept token; logs in first when none is kept or amuleapi
        refused it."""
        if self._token is not None:
            status, reply = self._send(
                method=method, path=_PREFERENCES_PATH, body=body, token=self._token
            )
            if status != HTTPStatus.UNAUTHORIZED:
                return status, reply
        self._token = self._log_in()
        return self._send(method=method, path=_PREFERENCES_PATH, body=body, token=self._token)

    def _log_in(self) -> str:
        status, login_reply = self._send(
            method="POST", path=_LOGIN_PATH, body={"password": self._api_password}, token=None
        )
        _raise_unless_success(
            status=status, message=f"POST {_LOGIN_PATH}: {status} {login_reply!r}"
        )
        try:
            token = json.loads(login_reply).get("token")
        except (ValueError, AttributeError):
            token = None
        if not (isinstance(token, str) and token):
            raise ListenPortError(
                f"amuleapi's login answered without a token ({login_reply[:100]!r})"
            )
        return token

    def _send(
        self, *, method: str, path: str, body: object, token: str | None
    ) -> tuple[int, bytes]:
        """The reply's status and body, its first 100 bytes on a refusal; raises when none came. A
        ``None`` body sends none."""
        headers: dict[str, str] = {}
        data: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self._api_url + path, data=data, headers=headers, method=method)
        try:
            with self._url_opener.open(request, timeout=self._timeout_seconds) as response:
                return int(response.status), response.read()
        except HTTPError as error:
            return error.code, _head(error)
        except (OSError, http.client.HTTPException) as error:
            # URLError and timeouts are OSErrors; a garbled reply is an HTTPException.
            failure = f"{method} {path}: {error}"
            if _is_not_ready(error.reason if isinstance(error, URLError) else error):
                raise ApiNotReadyError(failure) from error
            raise ListenPortError(failure) from error


def _is_not_ready(error: object) -> bool:
    """Refused before amuleapi's EC login, timed out while its one EC worker is busy."""
    return isinstance(error, ConnectionRefusedError | TimeoutError)


def _raise_unless_success(*, status: int, message: str) -> None:
    if status == HTTPStatus.SERVICE_UNAVAILABLE:
        # amuleapi answers 503 until its first snapshot of amuled.
        raise ApiNotReadyError(message)
    if not 200 <= status < 300:
        raise ListenPortError(message)


def _head(error: HTTPError) -> bytes:
    """The first 100 bytes of a refusal's body, none when it breaks off."""
    try:
        with error:  # an HTTPError holds the connection open until closed
            return error.read(100)
    except (OSError, http.client.HTTPException):
        return b""
