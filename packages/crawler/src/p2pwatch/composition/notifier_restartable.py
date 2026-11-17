"""The notifier as the node rebuilds it: no work runs over it, the dispatcher asks it for the
notifier at each send."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork


class AppriseNotifierBuilder(Protocol):
    def __call__(self) -> AppriseNotifier: ...


class NotifierRestartable(Restartable[SupervisedWork]):
    """The notifier the sends go to now, with the apprise objects it built: a rebuild builds it
    anew, and a send already under way finishes on the old one."""

    def __init__(self, *, build_notifier: AppriseNotifierBuilder) -> None:
        self._build_notifier = build_notifier
        self._notifier = build_notifier()

    def __str__(self) -> str:
        return "notifier"

    def notifier(self) -> AppriseNotifier:
        """The notifier built latest, which the next send goes to."""
        return self._notifier

    async def rebuild(self) -> Sequence[SupervisedWork]:
        """Builds the notifier anew; no work runs over it, so none is handed back."""
        self._notifier = self._build_notifier()
        return ()
