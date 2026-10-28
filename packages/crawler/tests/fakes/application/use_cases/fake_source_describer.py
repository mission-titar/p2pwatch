from dataclasses import dataclass
from datetime import datetime

from p2pwatch.application.ports.driving.source_describer import SourceDescriber, SourceDescription
from p2pwatch.domain.identifiers import SourceId


@dataclass(frozen=True)
class DescribeSourceCall:
    """The arguments of one ``describe_source`` call."""

    source_id: SourceId
    page: int
    requested_since: datetime | None
    requested_until: datetime | None


class FakeSourceDescriber(SourceDescriber):
    """Describes any source as it is given, and keeps each call's arguments."""

    def __init__(self, source_description: SourceDescription | None) -> None:
        self._source_description = source_description
        self.calls: list[DescribeSourceCall] = []

    def describe_source(
        self,
        source_id: SourceId,
        *,
        page: int,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> SourceDescription | None:
        self.calls.append(DescribeSourceCall(source_id, page, requested_since, requested_until))
        return self._source_description
