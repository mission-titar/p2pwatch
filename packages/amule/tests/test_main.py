"""``python -m p2pwatch_amule``: the command line wired to the real entry points."""

import pytest

from p2pwatch_amule.__main__ import main


@pytest.fixture(autouse=True)
def _refused_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each entry point refuses to start on its own variable, before it changes anything."""
    monkeypatch.delenv("PUID", raising=False)
    monkeypatch.setenv("GLUETUN_CONTROL_URL", "ftp://gluetun")


def test_boot_runs_the_boot_step() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["boot"])

    assert exit_info.value.code == "PUID is required"


def test_port_sync_runs_port_sync() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["port-sync"])

    assert str(exit_info.value.code).startswith("GLUETUN_CONTROL_URL must be an http or https URL")
