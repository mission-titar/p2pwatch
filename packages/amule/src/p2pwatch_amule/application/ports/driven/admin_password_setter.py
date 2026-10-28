from abc import ABC, abstractmethod

from p2pwatch_amule.domain.identifiers import Gid, Uid


class AdminPasswordSetter(ABC):
    """Sets amuleapi's admin password, which a non-loopback ``BindAddress`` needs to start."""

    @abstractmethod
    def set_admin_password(self, api_password: str, uid: Uid, gid: Gid) -> None:
        """Sets it to ``api_password``, its file owned by ``uid`` and ``gid``."""
