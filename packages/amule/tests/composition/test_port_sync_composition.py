"""Port-sync's assembly: gluetun and amuleapi as stand-ins."""

import logging
import socket
from datetime import timedelta
from urllib.request import ProxyHandler, build_opener

import pytest

from p2pwatch_amule.adapters.driven.gluetun_forwarded_port_client import (
    GluetunForwardedPortClient,
)
from p2pwatch_amule.application.port_sync_lifecycle import PortSyncLifecycle
from p2pwatch_amule.composition.port_sync_composition import PortSyncComposition
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock
from tests.fakes.fake_amule_api_server import FakeAmuleApiServer
from tests.fakes.fake_gluetun_control_server import FakeGluetunControlServer


class _Stop(Exception):
    pass


def _port_sync_composition(
    env: dict[str, str],
    *,
    monotonic_clock: FakeMonotonicClock,
    amule_api_url: str = "http://127.0.0.1:4711",
) -> PortSyncComposition:
    return PortSyncComposition(
        env=env,
        gluetun_url_opener=build_opener(ProxyHandler({})),
        amule_api_url=amule_api_url,
        amule_api_url_opener=build_opener(ProxyHandler({})),
        monotonic_clock=monotonic_clock,
    )


def test_port_sync_sets_gluetuns_port_live_under_its_modules_logger_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    monotonic_clock = FakeMonotonicClock()
    # gluetun has no port for a round, then it forwards 51820.
    with FakeGluetunControlServer() as gluetun, FakeAmuleApiServer() as amule_api:
        gluetun.body = b"{}"

        def between_rounds() -> None:
            if len(monotonic_clock.sleeps) == 2:
                raise _Stop
            gluetun.body = b'{"port": 51820}'

        monotonic_clock.on_sleep = between_rounds
        env = {
            "GLUETUN_CONTROL_URL": gluetun.control_url,
            "PORT_SYNC_POLL_SECONDS": "5",
            "AMULE_API_PASSWORD": amule_api.password,
        }
        port_sync_composition = _port_sync_composition(
            env, monotonic_clock=monotonic_clock, amule_api_url=amule_api.api_url
        )
        with caplog.at_level(logging.INFO), pytest.raises(_Stop):
            port_sync_composition.run_port_sync_loop()

    assert gluetun.request_lines == ["GET /v1/portforward HTTP/1.1"] * 2
    assert monotonic_clock.sleeps == [timedelta(seconds=5)] * 2
    assert amule_api.request_lines == [
        "POST /api/v1/auth/login?include_token=true HTTP/1.1",
        "GET /api/v1/preferences HTTP/1.1",
        "PATCH /api/v1/preferences HTTP/1.1",
    ]
    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        (GluetunForwardedPortClient.__module__, "gluetun reports no forwarded port (b'{}')"),
        (
            PortSyncLifecycle.__module__,
            "gluetun forwards 51820, amuled listened on 40123: set live",
        ),
    ]


def test_a_first_round_before_amuleapi_listens_leaves_amuled_running(
    caplog: pytest.LogCaptureFixture,
) -> None:
    monotonic_clock = FakeMonotonicClock()

    def stop() -> None:
        raise _Stop

    monotonic_clock.on_sleep = stop
    # amuleapi's starting state: it listens only once its EC login succeeded.
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        refusing_url = f"http://127.0.0.1:{closed.getsockname()[1]}"
    with FakeGluetunControlServer() as gluetun:
        env = {
            "GLUETUN_CONTROL_URL": gluetun.control_url,
            "AMULE_API_PASSWORD": "s3cret",
        }
        port_sync_composition = _port_sync_composition(
            env, monotonic_clock=monotonic_clock, amule_api_url=refusing_url
        )
        with caplog.at_level(logging.INFO), pytest.raises(_Stop):
            port_sync_composition.run_port_sync_loop()

    (not_ready,) = caplog.records
    assert not_ready.getMessage().startswith(
        "amuleapi is not ready, 51820 waits for the next poll (POST /api/v1/auth/login"
    )


def test_a_refused_variable_raises_before_any_round() -> None:
    env = {"GLUETUN_CONTROL_URL": "ftp://gluetun"}
    port_sync_composition = _port_sync_composition(env, monotonic_clock=FakeMonotonicClock())

    with pytest.raises(SettingsError, match="^GLUETUN_CONTROL_URL must be an http or https URL"):
        port_sync_composition.run_port_sync_loop()
