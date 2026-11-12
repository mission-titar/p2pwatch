"""``StateOwner`` port: what holds an in-memory state a restart can repair (spec v5 lot 4, D5)."""

from abc import ABC, abstractmethod


class StateOwner(ABC):
    """Built anew by its composition, the only place holding its factories."""

    @abstractmethod
    def __str__(self) -> str:
        """The owner as the log lines name it."""

    @abstractmethod
    async def restart(self) -> None:
        """Builds its state anew, then adds the works relying on it, if any, to the supervisor
        again, the supervisor having stopped the old ones."""
