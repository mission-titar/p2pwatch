"""The notifier as the node builds it, at its start and at each rebuild: built anew with the work
sending the outbox's notifications through it."""

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
from p2pwatch.domain.observability.notification_sends import NotificationService


class AppriseNotifierBuilder(Protocol):
    def __call__(self) -> AppriseNotifier: ...


# Every work over ``notifier``, such as the sending of the outbox's notifications through it.
class WorksOverNotifier(Protocol):
    def __call__(self, notifier: AppriseNotifier, /) -> Sequence[SupervisedWork]: ...


def notification_sending(
    sender: NotificationSender,
    *,
    notification_timeout_seconds: float,
    services: Sequence[NotificationService],
) -> Sequence[SupervisedWork]:
    """``sender``'s turns, each a send to one of ``services``, such as ``discord community``; none
    without a service, since nothing is then left to send."""
    if not services:
        return ()
    # One send per turn: its timeout, then the margin.
    time_limit = timedelta(seconds=notification_timeout_seconds) + TIME_LIMIT_MARGIN
    return [
        SupervisedWork(work=sender, time_limit=time_limit, function=CrawlerFunction.NOTIFICATIONS)
    ]


class NotifierRestartable(Restartable[SupervisedWork]):
    """The notifier the outbox's notifications go through, and the work sending them."""

    def __init__(self, notifier: AppriseNotifier, *, works: Sequence[SupervisedWork]) -> None:
        self.notifier = notifier
        self._works = tuple(works)

    def works(self) -> Sequence[SupervisedWork]:
        return self._works

    async def close(self) -> None:
        """Nothing to release: apprise holds no connection between two sends."""


class NotifierRestartableBuilder(RestartableBuilder[SupervisedWork]):
    """Builds the notifier anew with the work sending through it: a send under way at a rebuild
    keeps its entry for the new one."""

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
