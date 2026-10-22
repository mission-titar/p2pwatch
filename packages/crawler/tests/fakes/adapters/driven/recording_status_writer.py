from p2pwatch.application.ports.driven.client_status_writer import ClientStatusWriter
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import StatusReading


class RecordingStatusWriter(ClientStatusWriter):
    """Keeps each published reading with its client's name and its instant."""

    def __init__(self) -> None:
        self.published: list[tuple[str, StatusReading, MonotonicInstant]] = []

    def publish(
        self, client_name: str, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        self.published.append((client_name, reading, published_at))
