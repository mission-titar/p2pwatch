"""A notification's declared failures, and the notifier's component each outcome is recorded on,
judged on its bugs alone (spec v5 lot 4, D3, D10)."""

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS


class NotificationRefused(DeclaredFailure):
    """A service refused a notification or failed to deliver it: the ``Notifier``'s failure."""


class NotificationTimedOut(DeclaredFailure):
    """A send past the notification timeout: a reason, never raised."""


def notifier_component() -> Component:
    return Component(name="notifier", labels=ComponentLabels(), conditions=(BUGS,))
