"""CheckApiHealth: amuleapi's health as its client reads it."""

import pytest

from p2pwatch_amule.application.use_cases.check_api_health import CheckApiHealth
from tests.fakes.adapters.driven.fake_api_health_client import FakeApiHealthClient


@pytest.mark.parametrize("is_healthy", [True, False])
def test_the_health_is_amuleapi_s_health_read_once(is_healthy: bool) -> None:
    api_health_client = FakeApiHealthClient()
    api_health_client.is_healthy = is_healthy

    assert CheckApiHealth(api_health_client=api_health_client).check_api_health() is is_healthy

    assert api_health_client.reads == 1
