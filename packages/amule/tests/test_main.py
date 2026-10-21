"""``python -m p2pwatch_amule``: the command line wired to the real entry points."""

import logging
from typing import Any
from urllib.request import ProxyHandler, build_opener

import pytest

from p2pwatch_amule.__main__ import main
from p2pwatch_amule.domain.settings import PortSyncSettings, parse_port_sync_settings
from tests.fakes import FakeGluetunControlServer

IDS = {"PUID": "1000", "PGID": "1001"}


def _no_port_sync(port_sync_settings: PortSyncSettings, **components: Any) -> None:
    raise AssertionError("port-sync ran")


def test_boot_runs_the_boot_step(capsys: pytest.CaptureFixture[str]) -> None:
    # Refused on its first variable, before the boot step changes anything.
    assert main(["boot"], {}, build_opener(ProxyHandler({})), _no_port_sync) == 1

    assert capsys.readouterr().err == "PUID is required\n"


def test_port_sync_refuses_its_variables_before_running(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {**IDS, "GLUETUN_CONTROL_URL": "ftp://gluetun"}
    assert main(["port-sync"], env, build_opener(ProxyHandler({})), _no_port_sync) == 1

    assert capsys.readouterr().err.startswith("GLUETUN_CONTROL_URL must be an http or https URL")


def test_port_sync_runs_on_gluetuns_reader_under_the_two_documented_logger_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    received: list[tuple[PortSyncSettings, dict[str, Any]]] = []

    def run_port_sync(port_sync_settings: PortSyncSettings, **components: Any) -> None:
        received.append((port_sync_settings, components))

    with FakeGluetunControlServer() as gluetun:
        env = {**IDS, "GLUETUN_CONTROL_URL": gluetun.control_url, "PORT_SYNC_POLL_SECONDS": "5"}
        assert main(["port-sync"], env, gluetun.url_opener, run_port_sync) == 0
        [(port_sync_settings, components)] = received
        gluetun.body = b"{}"
        with caplog.at_level(logging.INFO):
            assert components["forwarded_port_reader"].read_forwarded_port() is None
            components["logger"].info("a port-sync line")

    assert port_sync_settings == parse_port_sync_settings(env)
    assert components["amule_conf_reader"] is components["amule_conf_writer"]
    assert gluetun.request_lines == ["GET /v1/portforward HTTP/1.1"]
    # The names docs/migration-4x.md gives the operator.
    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        ("p2pwatch_amule.adapters.driven.gluetun", "gluetun reports no forwarded port (b'{}')"),
        ("p2pwatch_amule.adapters.driving.port_sync", "a port-sync line"),
    ]
