"""Port-sync's assembly: gluetun's stand-in, amule.conf and s6 through their fakes."""

import logging
from datetime import timedelta
from urllib.request import ProxyHandler, build_opener

import pytest

from p2pwatch_amule.adapters.driven.gluetun_forwarded_port_client import (
    GluetunForwardedPortClient,
)
from p2pwatch_amule.application.port_sync_lifecycle import PortSyncLifecycle
from p2pwatch_amule.composition.port_sync_composition import PortSyncComposition
from p2pwatch_amule.domain.conf import with_listen_port
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes.adapters.driven.fake_amule_conf_store import FakeAmuleConfStore
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock
from tests.fakes.adapters.driven.fake_service_supervisor import FakeServiceSupervisor
from tests.fakes.fake_gluetun_control_server import FakeGluetunControlServer

CONF = "[eMule]\nPort=4662\nUDPPort=4672\n\n"


class _Stop(Exception):
    pass


def _port_sync_composition(
    env: dict[str, str], *, actions: list[str], monotonic_clock: FakeMonotonicClock
) -> tuple[PortSyncComposition, FakeAmuleConfStore]:
    amule_conf = FakeAmuleConfStore(actions)
    amule_conf.conf = CONF
    port_sync_composition = PortSyncComposition(
        env=env,
        amule_conf_reader=amule_conf,
        amule_conf_writer=amule_conf,
        service_supervisor=FakeServiceSupervisor(actions),
        url_opener=build_opener(ProxyHandler({})),
        monotonic_clock=monotonic_clock,
    )
    return port_sync_composition, amule_conf


def test_port_sync_restarts_amuled_on_gluetuns_port_under_its_modules_logger_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actions: list[str] = []
    monotonic_clock = FakeMonotonicClock()
    # gluetun has no port for a round, then it forwards 51820.
    with FakeGluetunControlServer() as gluetun:
        gluetun.body = b"{}"

        def between_rounds() -> None:
            if len(monotonic_clock.sleeps) == 2:
                raise _Stop
            gluetun.body = b'{"port": 51820}'

        monotonic_clock.on_sleep = between_rounds
        env = {
            "PUID": "1000",
            "PGID": "1001",
            "GLUETUN_CONTROL_URL": gluetun.control_url,
            "PORT_SYNC_POLL_SECONDS": "5",
        }
        port_sync_composition, amule_conf = _port_sync_composition(
            env, actions=actions, monotonic_clock=monotonic_clock
        )
        with caplog.at_level(logging.INFO), pytest.raises(_Stop):
            port_sync_composition.run_port_sync_loop()

    assert gluetun.request_lines == ["GET /v1/portforward HTTP/1.1"] * 2
    assert monotonic_clock.sleeps == [timedelta(seconds=5)] * 2
    assert actions == [
        "start amuled",
        "read amule.conf",
        "stop amuled",
        "read amule.conf",
        "write amule.conf as 1000:1001",
        "start amuled",
    ]
    assert amule_conf.conf == with_listen_port(CONF, port=51820)
    lifecycle = PortSyncLifecycle.__module__
    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        (GluetunForwardedPortClient.__module__, "gluetun reports no forwarded port (b'{}')"),
        (lifecycle, "gluetun forwards 51820, amuled listens on 4662: restarting amuled"),
        (lifecycle, "amule.conf now sets Port and UDPPort to 51820"),
    ]


def test_a_refused_variable_raises_before_amuled_is_started() -> None:
    actions: list[str] = []
    env = {"PUID": "1000", "PGID": "1001", "GLUETUN_CONTROL_URL": "ftp://gluetun"}
    port_sync_composition, _ = _port_sync_composition(
        env, actions=actions, monotonic_clock=FakeMonotonicClock()
    )

    with pytest.raises(SettingsError, match="^GLUETUN_CONTROL_URL must be an http or https URL"):
        port_sync_composition.run_port_sync_loop()

    assert actions == []
