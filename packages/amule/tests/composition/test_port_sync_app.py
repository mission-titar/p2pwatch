"""Port-sync's assembly: gluetun's stand-in, amule.conf in a directory, a recorded s6."""

import logging
from datetime import timedelta
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import pytest

from p2pwatch_amule.composition.port_sync_app import PortSyncApp
from p2pwatch_amule.domain.conf import with_listen_port
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes import FakeGluetunControlServer, FakeMonotonicClock, FakeS6

CONF = "[eMule]\nPort=4662\nUDPPort=4672\n\n"


class _Stop(Exception):
    pass


class _Ownership:
    """Records each chown: the gate cannot chown to another uid."""

    def __init__(self) -> None:
        self.owners: list[tuple[Path, int, int]] = []

    def change_owner(self, path: Path, uid: int, gid: int) -> None:
        self.owners.append((path, uid, gid))


def _port_sync_app(
    env: dict[str, str],
    tmp_path: Path,
    s6: FakeS6,
    ownership: _Ownership,
    monotonic_clock: FakeMonotonicClock,
) -> PortSyncApp:
    return PortSyncApp(
        env=env,
        amule_conf_path=tmp_path / "amule.conf",
        port_sync_service_directory=tmp_path / "port-sync",
        amuled_service_directory=tmp_path / "amuled",
        url_opener=build_opener(ProxyHandler({})),
        run_command=s6.run_command,
        change_owner=ownership.change_owner,
        monotonic_clock=monotonic_clock,
    )


def test_port_sync_restarts_amuled_on_gluetuns_port_under_the_two_documented_logger_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "amule.conf").write_text(CONF)
    s6, ownership, monotonic_clock = FakeS6(), _Ownership(), FakeMonotonicClock()
    # The first start fails, then gluetun has no port for a round, then it forwards 51820.
    s6.exit_code = 1
    with FakeGluetunControlServer() as gluetun:
        gluetun.body = b"{}"

        def between_rounds() -> None:
            if len(monotonic_clock.sleeps) == 2:
                raise _Stop
            s6.exit_code = 0
            gluetun.body = b'{"port": 51820}'

        monotonic_clock.on_sleep = between_rounds
        env = {
            "PUID": "1000",
            "PGID": "1001",
            "GLUETUN_CONTROL_URL": gluetun.control_url,
            "PORT_SYNC_POLL_SECONDS": "5",
        }
        app = _port_sync_app(env, tmp_path, s6, ownership, monotonic_clock)
        with caplog.at_level(logging.INFO), pytest.raises(_Stop):
            app.run_port_sync_loop()

    assert gluetun.request_lines == ["GET /v1/portforward HTTP/1.1"] * 2
    assert monotonic_clock.sleeps == [timedelta(seconds=5)] * 2
    amuled = str(tmp_path / "amuled")
    assert s6.commands == [
        ["s6-svc", "-u", amuled],
        ["s6-svc", "-wD", "-T", "60000", "-d", amuled],
        ["s6-svc", "-u", amuled],
    ]
    assert (tmp_path / "amule.conf").read_text() == with_listen_port(CONF, 51820)
    assert ownership.owners == [(tmp_path / "amule.conf.tmp", 1000, 1001)]
    # The names docs/migration-4x.md gives the operator.
    port_sync = "p2pwatch_amule.adapters.driving.port_sync"
    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        (port_sync, "s6-svc -u exited 1: timed out"),
        ("p2pwatch_amule.adapters.driven.gluetun", "gluetun reports no forwarded port (b'{}')"),
        (port_sync, "gluetun forwards 51820, amuled listens on 4662: restarting amuled"),
        (port_sync, "amule.conf now sets Port and UDPPort to 51820"),
    ]


def test_a_refused_variable_raises_before_amuled_is_started(tmp_path: Path) -> None:
    s6 = FakeS6()
    env = {"PUID": "1000", "PGID": "1001", "GLUETUN_CONTROL_URL": "ftp://gluetun"}
    app = _port_sync_app(env, tmp_path, s6, _Ownership(), FakeMonotonicClock())

    with pytest.raises(SettingsError, match="^GLUETUN_CONTROL_URL must be an http or https URL"):
        app.run_port_sync_loop()

    assert s6.commands == []
