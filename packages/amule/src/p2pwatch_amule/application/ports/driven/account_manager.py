from abc import ABC, abstractmethod


class AccountManager(ABC):
    """Holds the ``amule`` account amuled and amuleapi run as."""

    @abstractmethod
    def find_or_create_amule_account(self, uid: int, gid: int) -> None:
        """Creates the ``amule`` group with ``gid``, then the user with ``uid``, each if missing."""
