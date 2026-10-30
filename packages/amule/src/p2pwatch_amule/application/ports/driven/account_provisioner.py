from abc import ABC, abstractmethod

from p2pwatch_amule.domain.identifiers import Gid, Uid


class AccountProvisioner(ABC):
    """Holds the ``amule`` account amuled and amuleapi run as."""

    @abstractmethod
    def find_or_create_amule_account(self, uid: Uid, *, gid: Gid) -> None:
        """Creates the ``amule`` group with ``gid``, then the user with ``uid``, each if missing."""
