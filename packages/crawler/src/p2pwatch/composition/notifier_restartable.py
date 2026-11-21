"""The notifier as the node builds it, at its start and at each rebuild: built anew with the works
sending the outbox's notifications through it, one per service."""

from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.steps.notification_sender import NotificationSender
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.composition.work_time_limits import TIME_LIMIT_MARGIN
from p2pwatch.domain.crawler_function import CrawlerFunction


class AppriseNotifierBuilder(Protocol):
    def __call__(self) -> AppriseNotifier: ...


# Every work over ``notifier``, such as the sending of the outbox's notifications through it.
class WorksOverNotifier(Protocol):
    def __call__(self, notifier: AppriseNotifier, /) -> Sequence[SupervisedWork]: ...


def notification_sending(
    senders: Sequence[NotificationSender], *, notification_timeout_seconds: float
) -> Sequence[SupervisedWork]:
    """The turns of each of ``senders``, one per service, such as ``notification sending discord
    community``, each a work of its own, so that a service that never answers holds no other."""
    # One send per turn: its timeout, then the margin.
    time_limit = timedelta(seconds=notification_timeout_seconds) + TIME_LIMIT_MARGIN
    return [
        SupervisedWork(work=sender, time_limit=time_limit, function=CrawlerFunction.NOTIFICATIONS)
        for sender in senders
    ]


class NotifierRestartable(Restartable[SupervisedWork]):
    """The notifier the outbox's notifications go through, and the works sending them."""

    def __init__(self, notifier: AppriseNotifier, *, works: Sequence[SupervisedWork]) -> None:
        self.notifier = notifier
        self._works = tuple(works)

    def works(self) -> Sequence[SupervisedWork]:
        return self._works

    async def close(self) -> None:
        """Nothing to release: apprise holds no connection between two sends."""


class NotifierRestartableBuilder(RestartableBuilder[SupervisedWork]):
    """Builds the notifier anew with the works sending through it: a send under way at a rebuild
    keeps its entry for the new ones."""

    def __init__(
        self, *, build_notifier: AppriseNotifierBuilder, works_over: WorksOverNotifier
    ) -> None:
        self._build_notifier = build_notifier
        self._works_over = works_over

    def __str__(self) -> str:
        return "notifier"

    async def build(self) -> NotifierRestartable:
        notifier = self._build_notifier()
        return NotifierRestartable(notifier, works=self._works_over(notifier))
