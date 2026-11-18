"""The sends of the notifications: the services the notifier sends to, the error a refused send
raises, and each service's part, judged on its sends that failed and on its bugs."""

from collections.abc import Iterable
from dataclasses import dataclass

from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import Detections, HealthRule
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.work_components import BUGS


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


# A send refused or past the notification timeout is detected; a bug of the notifier is not.
SENDS_FAILED = HealthRule(
    name="sends failed",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)


def notification_service_components(
    services: Iterable[NotificationService],
) -> dict[NotificationService, Component]:
    """A part per service, judged on its sends that failed and on its bugs: "notifier discord
    community"."""
    return {
        service: Component(name=f"notifier {service}", rules=(BUGS, SENDS_FAILED))
        for service in services
    }
