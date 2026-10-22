"""``ContainerBooter``: prepares the aMule container, once, as root, before s6 starts."""

from abc import ABC, abstractmethod


class ContainerBooter(ABC):
    """Refuses the container's variables or prepares the container from them."""

    @abstractmethod
    def boot_container(self) -> None:
        """Raises ``SettingsError`` on the first refused variable, before any change."""
