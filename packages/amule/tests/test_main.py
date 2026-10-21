"""``python -m p2pwatch_amule``: the command line wired to the real driving ports."""

from urllib.request import ProxyHandler, build_opener

import pytest

from p2pwatch_amule.__main__ import main

IDS = {"PUID": "1000", "PGID": "1001"}


def test_boot_runs_the_boot_step(capsys: pytest.CaptureFixture[str]) -> None:
    # Refused on its first variable, before the boot step changes anything.
    assert main(["boot"], {}, build_opener(ProxyHandler({}))) == 1

    assert capsys.readouterr().err == "PUID is required\n"


def test_port_sync_refuses_its_variables_before_running(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {**IDS, "GLUETUN_CONTROL_URL": "ftp://gluetun"}
    assert main(["port-sync"], env, build_opener(ProxyHandler({}))) == 1

    assert capsys.readouterr().err.startswith("GLUETUN_CONTROL_URL must be an http or https URL")
