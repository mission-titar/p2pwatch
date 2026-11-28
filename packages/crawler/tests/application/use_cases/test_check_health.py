"""CheckHealth: the node's health as its endpoint's client reads it."""

import pytest

from p2pwatch.application.use_cases.check_health import CheckHealth
from tests.fakes.adapters.driven.fake_health_endpoint_client import FakeHealthEndpointClient


@pytest.mark.parametrize("is_healthy", [True, False])
def test_the_health_is_the_endpoint_s_read_once(is_healthy: bool) -> None:
    health_endpoint_client = FakeHealthEndpointClient(is_healthy=is_healthy)

    assert CheckHealth(health_endpoint_client=health_endpoint_client).check_health() is is_healthy

    assert health_endpoint_client.reads == 1
