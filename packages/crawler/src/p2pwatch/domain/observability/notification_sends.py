"""The sends of the notifications: the error a refused send raises, and the notifier's part, judged
on its sends that failed and on its bugs."""

from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import Detections, HealthRule
from p2pwatch.domain.work_components import BUGS


class NotificationRefusedError(ExpectedError):
    """A notification service refused a send, such as a Discord webhook answering 404."""


# A send refused or past the notification timeout is detected; a bug of the notifier is not.
SENDS_FAILED = HealthRule(
    name="sends failed",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)


def notifier_component() -> Component:
    """The notifier, judged on its sends that failed and on its bugs: "notifier"."""
    return Component(name="notifier", client_name=None, rules=(BUGS, SENDS_FAILED))
