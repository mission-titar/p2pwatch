from datetime import datetime, timedelta, timezone

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso


def test_utc_iso_is_fixed_width_and_normalizes_to_utc() -> None:
    # Fixed width (microseconds ALWAYS written) => lexicographic order == chronological.
    paris = timezone(timedelta(hours=2))
    moment = datetime(2026, 6, 11, 14, 0, 0, tzinfo=paris)
    assert utc_iso(moment) == "2026-06-11T12:00:00.000000+00:00"


def test_utc_iso_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match=r"^utc_iso requires an aware datetime$"):
        utc_iso(datetime(2026, 6, 11, 14, 0, 0))
