from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.policy import Audience, Severity


class FakeNotifier(Notifier):
    def __init__(self) -> None:
        self.calls: list[tuple[Audience, str, str, Severity]] = []
        self.node_ids: list[str] = []

    async def notify(
        self, audience: Audience, title: str, body: str, severity: Severity, node_id: str
    ) -> None:
        self.calls.append((audience, title, body, severity))
        self.node_ids.append(node_id)
