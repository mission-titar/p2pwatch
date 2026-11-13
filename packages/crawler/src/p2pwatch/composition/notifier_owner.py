"""The notifier's owner: the notifier and its apprise objects, one per URL, built anew by a restart;
the dispatcher reaches the notifier through it at each send (spec v5 lot 4, D5)."""

from typing import Protocol

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.application.ports.driven.state_owner import StateOwner


class NotifierBuilder(Protocol):
    def __call__(self) -> Notifier: ...


class NotifierOwner(StateOwner):
    """Holds the notifier each send reaches now; no work feeds its components, so a restart adds
    none."""

    def __init__(self, *, build_notifier: NotifierBuilder) -> None:
        self._build_notifier = build_notifier
        self._notifier = build_notifier()

    def __str__(self) -> str:
        return "owner of the notifier"

    def notifier(self) -> Notifier:
        """The notifier built latest."""
        return self._notifier

    async def restart(self) -> None:
        self._notifier = self._build_notifier()
