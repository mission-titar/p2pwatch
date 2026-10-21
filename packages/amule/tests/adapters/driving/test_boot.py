"""boot main: the booter first, then the admin pass and port-sync."""

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from p2pwatch_amule.adapters.driving import boot as entry
from p2pwatch_amule.domain.settings_error import SettingsError
from p2pwatch_amule.ports.driving.container_booter import ContainerBooter

ENV = {
    "PUID": "1000",
    "PGID": "1001",
    "AMULE_EC_PASSWORD": "hunter2",
    "AMULE_API_PASSWORD": "s3cret",
}

Call = tuple[list[str], dict[str, Any]]


class FakeContainerBooter(ContainerBooter):
    """Records each environment it boots in, or raises a set error."""

    def __init__(self) -> None:
        self.error: SettingsError | None = None
        self.envs: list[Mapping[str, str]] = []

    def boot_container(self, env: Mapping[str, str]) -> None:
        self.envs.append(env)
        if self.error is not None:
            raise self.error


class Boot:
    """main's paths under tmp_path, its environment, and its commands recorded."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.home = tmp_path / "home/amule"
        self.config = self.home / ".aMule"
        self.port_sync_down = tmp_path / "services.d/port-sync/down"
        self.port_sync_down.parent.mkdir(parents=True)
        self.env = dict(ENV)
        self.container_booter = FakeContainerBooter()
        self.calls: list[Call] = []
        monkeypatch.setattr(subprocess, "run", self._run)

    def main(self) -> None:
        entry.main(
            self.env,
            container_booter=self.container_booter,
            home_directory=self.home,
            config_directory=self.config,
            port_sync_down_file=self.port_sync_down,
        )

    def _run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    def set_admin_pass(self) -> Call:
        argv = ["amuleapi", f"--config-dir={self.config}", "--set-admin-pass=s3cret"]
        kwargs = {
            "user": 1000,
            "group": 1001,
            "extra_groups": [],
            "env": {**self.env, "HOME": str(self.home)},
            "check": True,
        }
        return argv, kwargs


@pytest.fixture
def boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Boot:
    return Boot(tmp_path, monkeypatch)


def test_boot_boots_the_container_then_sets_the_admin_password(boot: Boot) -> None:
    boot.main()
    assert boot.container_booter.envs == [boot.env]
    assert boot.calls == [boot.set_admin_pass()]


def test_the_admin_password_is_the_one_set(boot: Boot) -> None:
    boot.env["AMULE_API_PASSWORD"] = "mot de passé"
    boot.main()
    assert "--set-admin-pass=mot de passé" in boot.calls[-1][0]


def test_a_refused_variable_aborts_the_boot_before_any_change(boot: Boot) -> None:
    boot.container_booter.error = SettingsError("PUID is required")
    with pytest.raises(SettingsError, match="^PUID is required$"):
        boot.main()
    assert boot.calls == []
    assert not boot.port_sync_down.exists()


@pytest.mark.parametrize("value", ["off", "", None])
def test_port_sync_off_or_unset_keeps_its_service_down(boot: Boot, value: str | None) -> None:
    if value is not None:
        boot.env["PORT_SYNC"] = value
    boot.main()
    assert boot.port_sync_down.is_file()


@pytest.mark.parametrize("value", ["yes", "On"])
def test_port_sync_on_lets_s6_start_its_service(boot: Boot, value: str) -> None:
    boot.port_sync_down.touch()
    boot.env["PORT_SYNC"] = value
    boot.main()
    assert not boot.port_sync_down.exists()


def test_port_sync_on_without_a_down_file_boots(boot: Boot) -> None:
    boot.env["PORT_SYNC"] = "on"
    boot.main()
    assert not boot.port_sync_down.exists()
