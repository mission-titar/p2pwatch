"""The command line, wired to the real adapters and composition."""

import logging

import pytest

from p2pwatch_amule.composition.command_line import AMULE_API_URL, build_command_line
from tests.fakes.fake_amule_api_server import FakeAmuleApiServer

IDS = {"PUID": "1000", "PGID": "1001"}
# Never 4711: a node up on the same host publishes it on every interface.
_UNUSED_API_URL = "http://127.0.0.1:9"


def test_boot_runs_the_boot_step(capsys: pytest.CaptureFixture[str]) -> None:
    command_line = build_command_line(
        env={}, root_logger=logging.getLogger(), amule_api_url=_UNUSED_API_URL
    )

    # Refused on its first variable, before the boot step changes anything.
    assert command_line.run(["boot"]) == 1

    assert capsys.readouterr().err == "PUID is required\n"


def test_port_sync_refuses_its_variables_before_running(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {**IDS, "GLUETUN_CONTROL_URL": "ftp://gluetun"}
    command_line = build_command_line(
        env=env, root_logger=logging.getLogger(), amule_api_url=_UNUSED_API_URL
    )

    assert command_line.run(["port-sync"]) == 1

    assert capsys.readouterr().err.startswith("GLUETUN_CONTROL_URL must be an http or https URL")


def test_health_asks_amuleapi() -> None:
    with FakeAmuleApiServer() as amule_api:
        command_line = build_command_line(
            env={}, root_logger=logging.getLogger(), amule_api_url=amule_api.api_url
        )

        assert command_line.run(["health"]) == 0

    assert amule_api.request_lines == ["GET /api/v1/health HTTP/1.1"]


def test_amuleapi_is_asked_on_the_loopback_port_amuled_starts_it_on() -> None:
    assert AMULE_API_URL == "http://127.0.0.1:4711"
