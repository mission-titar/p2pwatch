"""boot main: the booter first, then port-sync's down file."""

from collections.abc import Mapping
from pathlib import Path

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
    """main's down file under tmp_path, its environment, and its booter."""

    def __init__(self, tmp_path: Path) -> None:
        self.port_sync_down = tmp_path / "services.d/port-sync/down"
        self.port_sync_down.parent.mkdir(parents=True)
        self.env = dict(ENV)
        self.container_booter = FakeContainerBooter()

    def main(self) -> None:
        entry.main(
            self.env,
            container_booter=self.container_booter,
            port_sync_down_file=self.port_sync_down,
        )


@pytest.fixture
def boot(tmp_path: Path) -> Boot:
    return Boot(tmp_path)


def test_boot_boots_the_container_in_its_environment(boot: Boot) -> None:
    boot.main()
    assert boot.container_booter.envs == [boot.env]


def test_a_refused_variable_aborts_the_boot_before_any_change(boot: Boot) -> None:
    boot.container_booter.error = SettingsError("PUID is required")
    with pytest.raises(SettingsError, match="^PUID is required$"):
        boot.main()
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
