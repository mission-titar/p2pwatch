"""``ShutdownRequester``: requests the crawler's graceful shutdown."""

from abc import ABC, abstractmethod


class ShutdownRequester(ABC):
    """Requests the crawler's graceful shutdown, from any thread."""

    @abstractmethod
    def request_shutdown(self) -> None:
        """Returns at once: the crawler stops, and the container restarts it."""
