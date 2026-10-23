"""What a ``Notifier`` sends an audience, each notification carrying the node that sent it."""

from dataclasses import dataclass

from p2pwatch.domain.observability.severity import Severity


@dataclass(frozen=True)
class RelayedLogLine:
    """An event's log line, relayed unchanged: it has no text of its own."""

    message: str
    severity: Severity
    node_id: str


@dataclass(frozen=True)
class TextNotification:
    """A notification with its own title and Markdown body, written by the domain."""

    title: str
    body: str
    severity: Severity
    node_id: str


type Notification = TextNotification | RelayedLogLine
