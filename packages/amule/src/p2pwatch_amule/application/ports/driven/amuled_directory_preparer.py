from abc import ABC, abstractmethod

from p2pwatch_amule.domain.identifiers import Gid, Uid


class AmuledDirectoryPreparer(ABC):
    """Holds the directories amuled and amuleapi write under: the mount points and the home."""

    @abstractmethod
    def prepare_amuled_directories(self, uid: Uid, *, gid: Gid) -> None:
        """Creates each directory if missing, owned by ``uid`` and ``gid``, not its content."""
