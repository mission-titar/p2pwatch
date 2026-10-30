from dataclasses import dataclass
from datetime import datetime

from p2pwatch.application.ports.driving.source_name_describer import (
    SourceNameDescriber,
    SourceNameDescription,
)


@dataclass(kw_only=True, frozen=True)
class DescribeSourceNameCall:
    """The arguments of one ``describe_source_name`` call."""

    source_name: str
    page: int
    requested_since: datetime | None
    requested_until: datetime | None


class FakeSourceNameDescriber(SourceNameDescriber):
    """Describes any source name as it is given, and keeps each call's arguments."""

    def __init__(self, source_name_description: SourceNameDescription | None) -> None:
        self._source_name_description = source_name_description
        self.calls: list[DescribeSourceNameCall] = []

    def describe_source_name(
        self,
        source_name: str,
        *,
        page: int,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> SourceNameDescription | None:
        call = DescribeSourceNameCall(
            source_name=source_name,
            page=page,
            requested_since=requested_since,
            requested_until=requested_until,
        )
        self.calls.append(call)
        return self._source_name_description
