"""A notification's declared failures, the services a notifier sends to, and each service's
component, judged on its bugs and on its sends refused (spec v5 lot 4, D3, D10)."""

from collections.abc import Iterable
from dataclasses import dataclass

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS, HealthCondition
from p2pwatch.domain.health.outcome import OutcomeSource
from p2pwatch.domain.observability.policy import Audience


class NotificationRefused(DeclaredFailure):
    """A service refused a notification or failed to deliver it: the ``Notifier``'s failure."""


class NotificationTimedOut(DeclaredFailure):
    """A send past the notification timeout: a reason, never raised."""


SENDS = OutcomeSource(name="a notification's success or declared failure")
SENDS_REFUSED = HealthCondition(name="sends refused", source=SENDS, counting=NotificationRefused)


@dataclass(kw_only=True, frozen=True)
class NotificationService:
    """One service a notifier sends to, named by its scheme and its audience, never by its URL,
    which carries a webhook's token."""

    scheme: str
    audience: Audience
    ordinal: int = 1  # its rank among the services of its scheme and audience

    def __str__(self) -> str:
        named = f"{self.scheme} {self.audience.value}"
        return named if self.ordinal == 1 else f"{named} {self.ordinal}"


def notifier_components(
    services: Iterable[NotificationService],
) -> dict[NotificationService, Component]:
    """A component per service, each outcome of its sends recorded on it."""
    return {
        service: Component(
            name=f"notifier {service}",
            labels=ComponentLabels(),
            conditions=(BUGS, SENDS_REFUSED),
        )
        for service in services
    }
