from p2pwatch_amule.application.ports.driving.container_booter import ContainerBooter
from p2pwatch_amule.domain.settings_error import SettingsError


class FakeContainerBooter(ContainerBooter):
    """Counts its boots, or raises a set error."""

    def __init__(self) -> None:
        self.error: SettingsError | None = None
        self.boots = 0

    def boot_container(self) -> None:
        self.boots += 1
        if self.error is not None:
            raise self.error
