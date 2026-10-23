from p2pwatch.application.ports.driven.event_emitter import EventEmitter
from p2pwatch.domain.observability.events import Event


class FakeEventEmitter(EventEmitter):
    """Captures emitted events (the test asserts the sequence)."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.node_ids: set[str] = set()  # every call's

    async def emit(self, event: Event, node_id: str) -> None:
        self.events.append(event)
        self.node_ids.add(node_id)
