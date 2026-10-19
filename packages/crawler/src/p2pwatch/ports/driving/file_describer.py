"""``FileDescriber``: describes one catalogued file over an interval."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from catalog_matching.domain.engine import Explanation
from p2pwatch.domain.file_history import FileHistory
from p2pwatch.domain.interval import Interval
from p2pwatch.domain.sharing_period import SharingPeriod


@dataclass(frozen=True)
class FileDescription:
    file_history: FileHistory
    sharing_periods: tuple[SharingPeriod, ...]  # newest first
    explanation: Explanation | None  # its first decision against the current policy
    interval: Interval  # the one read, resolved from the request
    now: datetime  # to the second: the interval's presets end there


class FileDescriber(ABC):
    """Describes a file from any thread."""

    @abstractmethod
    def describe_file(
        self,
        file_id: bytes,
        *,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> FileDescription | None:
        """The file over the interval requested; ``None`` for a file the catalog does not
        hold."""
