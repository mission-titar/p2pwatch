"""Port-sync's assembly: gluetun's stand-in, amule.conf in a directory, s6's commands recorded."""

import logging
from datetime import timedelta
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import pytest

from p2pwatch_amule.composition.port_sync_composition import PortSyncComposition
from p2pwatch_amule.domain.conf import with_listen_port
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes.adapters.driven.fake_command_runner import FakeCommandRunner
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock
from tests.fakes.adapters.driven.fake_ownership import FakeOwnership
from tests.fakes.fake_gluetun_control_server import FakeGluetunControlServer

CONF = "[eMule]\nPort=4662\nUDPPort=4672\n\n"
CAPTURED = {"capture_output": True, "text": True}


class _Stop(Exception):
    pass


def _port_sync_composition(
    env: dict[str, str],
    tmp_path: Path,
    command_runner: FakeCommandRunner,
    ownership: FakeOwnership,
    monotonic_clock: FakeMonotonicClock,
) -> PortSyncComposition:
    return PortSyncComposition(
        env=env,
        amule_conf_path=tmp_path / "amule.conf",
        port_sync_service_directory=tmp_path / "port-sync",
        amuled_service_directory=tmp_path / "amuled",
        url_opener=build_opener(ProxyHandler({})),
        run_command=command_runner.run_command,
        change_owner=ownership.change_owner,
        monotonic_clock=monotonic_clock,
    )


def test_port_sync_restarts_amuled_on_gluetuns_port_under_the_two_documented_logger_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "amule.conf").write_text(CONF)
    command_runner, ownership = FakeCommandRunner(), FakeOwnership()
    monotonic_clock = FakeMonotonicClock()
    # The first start fails, then gluetun has no port for a round, then it forwards 51820.
    command_runner.exit_code, command_runner.stderr = 1, "timed out\n"
    with FakeGluetunControlServer() as gluetun:
        gluetun.body = b"{}"

        def between_rounds() -> None:
            if len(monotonic_clock.sleeps) == 2:
                raise _Stop
            command_runner.exit_code = 0
            gluetun.body = b'{"port": 51820}'

        monotonic_clock.on_sleep = between_rounds
        env = {
            "PUID": "1000",
            "PGID": "1001",
            "GLUETUN_CONTROL_URL": gluetun.control_url,
            "PORT_SYNC_POLL_SECONDS": "5",
        }
        port_sync_composition = _port_sync_composition(
            env, tmp_path, command_runner, ownership, monotonic_clock
        )
        with caplog.at_level(logging.INFO), pytest.raises(_Stop):
            port_sync_composition.run_port_sync_loop()

    assert gluetun.request_lines == ["GET /v1/portforward HTTP/1.1"] * 2
    assert monotonic_clock.sleeps == [timedelta(seconds=5)] * 2
    amuled = str(tmp_path / "amuled")
    assert command_runner.commands == [
        (["s6-svc", "-u", amuled], CAPTURED),
        (["s6-svc", "-wD", "-T", "60000", "-d", amuled], CAPTURED),
        (["s6-svc", "-u", amuled], CAPTURED),
    ]
    assert (tmp_path / "amule.conf").read_text() == with_listen_port(CONF, 51820)
    assert ownership.chowns == [(tmp_path / "amule.conf.tmp", 1000, 1001)]
    # The names docs/migration-4x.md gives the operator.
    port_sync = "p2pwatch_amule.adapters.driving.port_sync"
    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        (port_sync, "s6-svc -u exited 1: timed out"),
        ("p2pwatch_amule.adapters.driven.gluetun", "gluetun reports no forwarded port (b'{}')"),
        (port_sync, "gluetun forwards 51820, amuled listens on 4662: restarting amuled"),
        (port_sync, "amule.conf now sets Port and UDPPort to 51820"),
    ]


def test_a_refused_variable_raises_before_amuled_is_started(tmp_path: Path) -> None:
    command_runner = FakeCommandRunner()
    env = {"PUID": "1000", "PGID": "1001", "GLUETUN_CONTROL_URL": "ftp://gluetun"}
    port_sync_composition = _port_sync_composition(
        env, tmp_path, command_runner, FakeOwnership(), FakeMonotonicClock()
    )

    with pytest.raises(SettingsError, match="^GLUETUN_CONTROL_URL must be an http or https URL"):
        port_sync_composition.run_port_sync_loop()

    assert command_runner.commands == []
