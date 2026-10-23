from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.policy import Audience, Severity
from tests.fakes.adapters.driven.fake_time import FakeTime


class FakeTimedNotifier(Notifier):
    """Each notification's body with the seconds elapsed on the monotonic clock when it was sent."""

    def __init__(self, fake_time: FakeTime) -> None:
        self._fake_time = fake_time
        self._start = fake_time.monotonic.now()
        self.bodies: list[tuple[float, str]] = []
        self.node_ids: set[str] = set()  # every call's

    async def notify(
        self, audience: Audience, title: str, body: str, severity: Severity, node_id: str
    ) -> None:
        elapsed = self._fake_time.monotonic.now() - self._start
        self.bodies.append((elapsed.total_seconds(), body))
        self.node_ids.add(node_id)
