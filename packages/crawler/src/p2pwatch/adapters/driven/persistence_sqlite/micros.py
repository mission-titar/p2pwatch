"""The stores' conversions between an instant and its integer of microseconds since the epoch."""

import warnings
from datetime import UTC, datetime, timedelta

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)


def instant_to_micros(instant: datetime) -> int:
    """Microseconds since the Unix epoch of an aware instant; a naive one raises ``ValueError``."""
    if instant.tzinfo is None:
        raise ValueError("instant_to_micros requires an aware datetime")
    return (instant - _EPOCH) // _MICROSECOND


def micros_to_instant(micros: int) -> datetime:
    """The aware UTC instant ``micros`` microseconds after the Unix epoch."""
    return _EPOCH + micros * _MICROSECOND


# category=None: no runtime warning, which under -W error would fail the migration calling it.
@warnings.deprecated(
    "Only the migrations call it, in SQL, to read the text stamps of an older database",
    category=None,
)
def iso_to_micros(stamp: str) -> int:
    """Microseconds since the Unix epoch of an aware ISO-8601 stamp; a naive one raises."""
    return instant_to_micros(datetime.fromisoformat(stamp))
