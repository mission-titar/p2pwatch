from abc import ABC, abstractmethod


class AdminPasswordSetter(ABC):
    """Sets amuleapi's admin password, which a non-loopback ``BindAddress`` needs to start."""

    @abstractmethod
    def set_admin_password(self, api_password: str, uid: int, gid: int) -> None:
        """Sets it to ``api_password``, its file owned by ``uid`` and ``gid``."""
