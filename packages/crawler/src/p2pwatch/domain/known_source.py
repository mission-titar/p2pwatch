"""A source the catalog knows by its user hash, as the sources list shows it."""

from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.source import SourceKey


@dataclass(frozen=True)
class KnownSource:
    """A source with a user hash, the latest name it carried, its latest reading and its files."""

    source: SourceKey
    source_name: str | None  # None when no reading had one
    last_seen_at: datetime
    file_count: int
