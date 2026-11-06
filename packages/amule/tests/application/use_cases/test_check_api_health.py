"""CheckApiHealth: amuleapi's health as its client reads it."""

import pytest

from p2pwatch_amule.application.use_cases.check_api_health import CheckApiHealth
from tests.fakes.adapters.driven.fake_api_health_client import FakeApiHealthClient


@pytest.mark.parametrize("is_ready", [True, False])
def test_the_health_is_amuleapi_s_readiness_read_once(is_ready: bool) -> None:
    api_health_client = FakeApiHealthClient()
    api_health_client.is_ready = is_ready

    assert CheckApiHealth(api_health_client=api_health_client).check_api_health() is is_ready

    assert api_health_client.reads == 1
