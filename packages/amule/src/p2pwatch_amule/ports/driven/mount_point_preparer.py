from abc import ABC, abstractmethod


class MountPointPreparer(ABC):
    """Holds the directories amuled and amuleapi write under: the mount points and the home."""

    @abstractmethod
    def prepare_mount_points(self, uid: int, gid: int) -> None:
        """Creates each directory if missing, owned by ``uid`` and ``gid``, not its content."""
