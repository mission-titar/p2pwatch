import httpx
import pytest

from p2pwatch.adapters.driven.amule_api.errors import (
    ApiAuthError,
    ApiError,
    ApiKadExhaustedError,
    ApiNotFoundError,
    ApiRejectedError,
    ApiUnreachableError,
    error_from_response,
)
from p2pwatch.domain.client_errors import (
    ClientError,
    ClientUnreachableError,
    DownloadRejectedError,
    SearchFailedError,
)
from tests.fakes.fake_amule_api import error


def _sent(response: httpx.Response) -> httpx.Response:
    """``response`` as the answer to a status read, the request its detail names."""
    response.request = httpx.Request("GET", "http://amuled.test:4711/api/v1/status")
    return response


def test_transport_failures_are_unreachable() -> None:
    assert issubclass(ApiUnreachableError, ClientUnreachableError)


def test_a_refusal_inherits_no_port_error() -> None:
    # amuleapi answers every refused operation with one code: each method names its own refusal.
    assert not issubclass(ApiRejectedError, ClientError)


def test_auth_error_is_not_a_loop_error() -> None:
    # An auth failure is a config problem (fail-fast at startup), not a loop case.
    assert issubclass(ApiAuthError, ClientError)
    assert not issubclass(ApiAuthError, ClientUnreachableError)
    assert not issubclass(ApiAuthError, SearchFailedError)
    assert not issubclass(ApiAuthError, DownloadRejectedError)


@pytest.mark.parametrize(
    ("status", "code", "mapped"),
    [
        (409, "kad_more_exhausted", ApiKadExhaustedError),
        (404, "not_found", ApiNotFoundError),
        (400, "amuled_rejected", ApiRejectedError),
    ],
)
def test_a_refused_operation_maps_to_its_rejection(
    status: int, code: str, mapped: type[ApiError]
) -> None:
    assert type(error_from_response(_sent(error(status, code)))) is mapped


def test_a_broken_ec_link_is_an_unreachable_daemon() -> None:
    """503 ec_unavailable: amuleapi is up, its link to amuled is not (a NEW state)."""
    response = _sent(error(503, "ec_unavailable", "cold"))
    assert type(error_from_response(response)) is ApiUnreachableError


def test_a_rate_limited_answer_carries_its_retry_delay() -> None:
    response = _sent(error(429, "rate_limited", "locked out", **{"Retry-After": "300"}))
    mapped = error_from_response(response)
    assert type(mapped) is ApiUnreachableError
    assert str(mapped) == "GET /api/v1/status: 429 rate_limited: locked out (retry after 300s)"


def test_an_error_body_that_is_not_an_envelope_still_maps() -> None:
    mapped = error_from_response(_sent(httpx.Response(500, content=b"oops")))
    assert type(mapped) is ApiUnreachableError
    assert str(mapped) == "GET /api/v1/status: 500 : Internal Server Error"


def test_an_error_envelope_with_junk_fields_still_maps() -> None:
    response = _sent(httpx.Response(500, json={"error": {"code": 7, "message": None}}))
    mapped = error_from_response(response)
    assert type(mapped) is ApiUnreachableError
    assert str(mapped) == "GET /api/v1/status: 500 : Internal Server Error"


def test_an_error_body_whose_error_key_is_not_an_object_still_maps() -> None:
    mapped = error_from_response(_sent(httpx.Response(500, json={"error": 7})))
    assert type(mapped) is ApiUnreachableError
    assert str(mapped) == "GET /api/v1/status: 500 : Internal Server Error"
