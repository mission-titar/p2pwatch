"""The sends of the notifications: the services the notifier sends to, a notification left to send
to one or saved unreadable, the error a refused send raises, each service's part, judged on its
sends that failed, and the local database's, judged on the saves of the notifications left."""

from collections.abc import Iterable
from dataclasses import dataclass

from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthAlert
from p2pwatch.domain.health.health_rule import Detections, HealthRule
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import (
    NotificationServiceSendsFailing,
    NotificationServiceSendsPassingAgain,
    NotificationsNotSaved,
    NotificationsSavedAgain,
)
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.policy import Audience


class NotificationRefusedError(ExpectedError):
    """A notification service refused a send, such as a Discord webhook answering 404."""


@dataclass(kw_only=True, frozen=True)
class NotificationService:
    """One service the notifier sends to, such as a Discord webhook for the community: named by
    its URL's scheme and its audience, never by its URL, which carries the webhook's token."""

    scheme: str
    audience: Audience
    ordinal: int = 1  # a second Discord webhook for the community is "discord community 2"

    def __str__(self) -> str:
        named = f"{self.scheme} {self.audience.value}"
        return named if self.ordinal == 1 else f"{named} {self.ordinal}"


@dataclass(kw_only=True, frozen=True)
class PendingNotification:
    """A notification left to send to one service, such as a tier rise for the community's
    Discord webhook: one entry of the outbox."""

    notification: Notification
    service: NotificationService


@dataclass(kw_only=True, frozen=True)
class UnreadableNotification:
    """An entry saved last that this version cannot read back, such as one an earlier version
    left without a field added since: dropped at the start."""

    reason: str  # "a stored value cannot be read: ..."


# A send refused or past the notification timeout is detected; a bug of the notifier is not.
SENDS_FAILED = HealthRule(
    name="sends failed",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)


# A save of the notifications left that the local database refused, such as on a full disk.
SAVES_FAILED = HealthRule(
    name="saves failed",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)


def local_database_dependency(*, node_id: NodeId) -> ExternalDependency:
    """The local database, judged on the saves of the notifications left: "local database"."""
    alert = HealthAlert(
        when_failing=NotificationsNotSaved(node_id=node_id),
        when_healthy_again=NotificationsSavedAgain(node_id=node_id),
    )
    return ExternalDependency(name="local database", client_name=None, rules={SAVES_FAILED: alert})


def notification_service_dependencies(
    services: Iterable[NotificationService], *, node_id: NodeId
) -> dict[NotificationService, ExternalDependency]:
    """A part per service, judged on its sends that failed: "notifier discord community"."""
    return {
        service: ExternalDependency(
            name=f"notifier {service}",
            client_name=None,
            rules={SENDS_FAILED: _sends_failed_alert(service, node_id=node_id)},
        )
        for service in services
    }


def _sends_failed_alert(service: NotificationService, *, node_id: NodeId) -> HealthAlert:
    return HealthAlert(
        when_failing=NotificationServiceSendsFailing(service_name=str(service), node_id=node_id),
        when_healthy_again=NotificationServiceSendsPassingAgain(
            service_name=str(service), node_id=node_id
        ),
    )
