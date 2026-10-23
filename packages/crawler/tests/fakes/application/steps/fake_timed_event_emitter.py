from p2pwatch.application.ports.driven.event_emitter import EventEmitter
from p2pwatch.domain.observability import events as ev
from tests.fakes.adapters.driven.fake_time import FakeTime


class FakeTimedEventEmitter(EventEmitter):
    """Each event with the seconds elapsed on the monotonic clock when it was emitted."""

    def __init__(self, fake_time: FakeTime) -> None:
        self._fake_time = fake_time
        self._start = fake_time.monotonic.now()
        self.events: list[tuple[float, ev.Event]] = []
        self.node_ids: set[str] = set()  # every call's

    async def emit(self, event: ev.Event, node_id: str) -> None:
        elapsed = self._fake_time.monotonic.now() - self._start
        self.events.append((elapsed.total_seconds(), event))
        self.node_ids.add(node_id)
