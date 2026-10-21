"""``python -m p2pwatch_amule``: the command line wired to the real entry points."""

import pytest

from p2pwatch_amule.__main__ import main


def test_boot_runs_the_boot_step() -> None:
    # Refused on its first variable, before the boot step changes anything.
    with pytest.raises(SystemExit) as exit_info:
        main(["boot"], {})

    assert exit_info.value.code == "PUID is required"


def test_port_sync_runs_port_sync(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["port-sync"], {"GLUETUN_CONTROL_URL": "ftp://gluetun"}) == 1

    assert capsys.readouterr().err.startswith("GLUETUN_CONTROL_URL must be an http or https URL")
