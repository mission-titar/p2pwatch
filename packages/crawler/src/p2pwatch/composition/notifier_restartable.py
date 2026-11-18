"""The notifier as the node builds it at each restart: no work runs over it, the dispatcher's
sends reach it."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.steps.work import SupervisedWork


class AppriseNotifierBuilder(Protocol):
    def __call__(self) -> AppriseNotifier: ...


class NotifierRestartable(Restartable[SupervisedWork]):
    """The notifier the sends go to, with the apprise objects it builds; no work runs over it."""

    def __init__(self, notifier: AppriseNotifier) -> None:
        self.notifier = notifier

    def works(self) -> Sequence[SupervisedWork]:
        return ()

    async def close(self) -> None:
        """Nothing to release: apprise holds no connection between two sends."""


class NotifierRestartableBuilder(RestartableBuilder[NotifierRestartable]):
    """Builds the notifier anew; a send already under way finishes on the one before."""

    def __init__(self, *, build_notifier: AppriseNotifierBuilder) -> None:
        self._build_notifier = build_notifier

    def __str__(self) -> str:
        return "notifier"

    async def build(self) -> NotifierRestartable:
        return NotifierRestartable(self._build_notifier())
