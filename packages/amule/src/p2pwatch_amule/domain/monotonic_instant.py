"""An instant of the monotonic clock: every interval and deadline kept in memory."""

from dataclasses import dataclass
from datetime import timedelta


@dataclass(kw_only=True, frozen=True)
class MonotonicInstant:
    """Never persisted nor displayed: its origin changes with each process. Its arithmetic refuses
    a ``datetime``, for mypy and at run time."""

    nanoseconds: int

    def __sub__(self, other: "MonotonicInstant") -> timedelta:
        if not isinstance(other, MonotonicInstant):
            return NotImplemented
        return timedelta(microseconds=(self.nanoseconds - other.nanoseconds) / 1000)
