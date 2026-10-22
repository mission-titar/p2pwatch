from collections.abc import Mapping

from p2pwatch_amule.application.ports.driving.container_booter import ContainerBooter
from p2pwatch_amule.domain.settings_error import SettingsError


class FakeContainerBooter(ContainerBooter):
    """Records each environment it boots in, or raises a set error."""

    def __init__(self) -> None:
        self.error: SettingsError | None = None
        self.envs: list[Mapping[str, str]] = []

    def boot_container(self, env: Mapping[str, str]) -> None:
        self.envs.append(env)
        if self.error is not None:
            raise self.error
