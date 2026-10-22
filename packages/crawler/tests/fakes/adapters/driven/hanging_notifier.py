import asyncio

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.policy import Audience, Severity


class HangingNotifier(Notifier):
    async def notify(
        self, audience: Audience, title: str, body: str, severity: Severity, node_id: str
    ) -> None:
        await asyncio.sleep(10)  # exceeds the test's short timeout
