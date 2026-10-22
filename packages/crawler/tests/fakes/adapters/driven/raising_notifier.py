from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.policy import Audience, Severity


class FakeRaisingNotifier(Notifier):
    async def notify(
        self, audience: Audience, title: str, body: str, severity: Severity, node_id: str
    ) -> None:
        raise RuntimeError("canal mort")
