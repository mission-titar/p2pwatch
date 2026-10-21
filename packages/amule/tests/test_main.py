"""``python -m p2pwatch_amule``: the command line wired to the real entry points."""

import logging
from typing import Any
from urllib.request import ProxyHandler, build_opener

import pytest

from p2pwatch_amule.__main__ import main
from p2pwatch_amule.domain.settings import parse_port_sync_settings
from p2pwatch_amule.ports.driving.port_sync_loop_runner import PortSyncLoopRunner
from tests.fakes import FakeGluetunControlServer

IDS = {"PUID": "1000", "PGID": "1001"}


class FakePortSyncLoopRunner(PortSyncLoopRunner):
    """Keeps what it was built on, counts its runs."""

    def __init__(self, components: dict[str, Any]) -> None:
        self.components = components
        self.runs = 0

    def run_port_sync_loop(self) -> None:
        self.runs += 1


def _no_port_sync(**components: Any) -> PortSyncLoopRunner:
    raise AssertionError("port-sync was built")


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
    built: list[FakePortSyncLoopRunner] = []

    def create_port_sync_loop_runner(**components: Any) -> PortSyncLoopRunner:
        built.append(FakePortSyncLoopRunner(components))
        return built[-1]

    with FakeGluetunControlServer() as gluetun:
        env = {**IDS, "GLUETUN_CONTROL_URL": gluetun.control_url, "PORT_SYNC_POLL_SECONDS": "5"}
        assert main(["port-sync"], env, gluetun.url_opener, create_port_sync_loop_runner) == 0
        [port_sync_loop_runner] = built
        components = port_sync_loop_runner.components
        gluetun.body = b"{}"
        with caplog.at_level(logging.INFO):
            assert components["forwarded_port_reader"].read_forwarded_port() is None
            components["logger"].info("a port-sync line")

    assert port_sync_loop_runner.runs == 1
    assert components["port_sync_settings"] == parse_port_sync_settings(env)
    assert components["amule_conf_reader"] is components["amule_conf_writer"]
    assert gluetun.request_lines == ["GET /v1/portforward HTTP/1.1"]
    # The names docs/migration-4x.md gives the operator.
    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        ("p2pwatch_amule.adapters.driven.gluetun", "gluetun reports no forwarded port (b'{}')"),
        ("p2pwatch_amule.adapters.driving.port_sync", "a port-sync line"),
    ]
