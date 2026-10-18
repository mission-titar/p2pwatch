from datetime import UTC, datetime

import pytest

from p2pwatch.webui.domain.format import (
    average_rate,
    human_size,
    input_timestamp,
    micros_timestamp,
    seasonal_locator,
    short_hash,
    short_timestamp,
    utc_timestamp,
)

pytestmark = pytest.mark.usefixtures("close_test_connections")

# Tuesday 2026-10-13 20:00:00 UTC, in microseconds since the Unix epoch.
TUESDAY_8PM = 1_791_921_600_000_000


def test_short_hash_truncates_with_ellipsis() -> None:
    assert short_hash("a" * 32) == "aaaaaaaa…"


def test_short_hash_short_input_is_unchanged() -> None:
    assert short_hash("abc") == "abc"


# ---------------------------------------------------------------------------
# human_size — binary (1024-based) units, matching this codebase's existing
# ``size_mib`` convention (see adapters/matching_read.py: "binary Mio").
# ---------------------------------------------------------------------------


def test_human_size_zero_bytes() -> None:
    assert human_size(0) == "0 B"


def test_human_size_just_under_kib_stays_in_bytes() -> None:
    assert human_size(1023) == "1023 B"


def test_human_size_exact_kib_boundary() -> None:
    assert human_size(1024) == "1 KB"


def test_human_size_kb_range_rounds_to_nearest() -> None:
    assert human_size(1_048_000) == "1023 KB"


def test_human_size_exact_mib_boundary() -> None:
    assert human_size(1024 * 1024) == "1 MB"


def test_human_size_matches_task_brief_example() -> None:
    """349 MiB — the exact example from the task brief."""
    assert human_size(349 * 1024 * 1024) == "349 MB"


def test_human_size_exact_gib_boundary() -> None:
    assert human_size(1024**3) == "1 GB"


def test_human_size_multi_gb() -> None:
    assert human_size(5 * 1024**3) == "5 GB"


def test_human_size_exact_tib_boundary() -> None:
    assert human_size(1024**4) == "1 TB"


def test_human_size_multi_tb() -> None:
    assert human_size(2 * 1024**4) == "2 TB"


def test_human_size_just_under_mib_promotes_to_mb() -> None:
    # Rounding 1024**2 - 1 bytes / 1024 lands exactly on 1024 (KB) — must promote to "1 MB",
    # not render "1024 KB".
    assert human_size(1024**2 - 1) == "1 MB"


def test_human_size_just_under_gib_promotes_to_gb() -> None:
    assert human_size(1024**3 - 1) == "1 GB"


def test_human_size_just_under_tib_promotes_to_tb() -> None:
    assert human_size(1024**4 - 1) == "1 TB"


# ---------------------------------------------------------------------------
# short_timestamp
# ---------------------------------------------------------------------------


def test_short_timestamp_with_microseconds_and_offset() -> None:
    assert short_timestamp("2026-07-03T23:45:24.104990+00:00") == "2026-07-03 23:45Z"


def test_short_timestamp_without_microseconds() -> None:
    assert short_timestamp("2026-07-03T23:45:24+00:00") == "2026-07-03 23:45Z"


def test_short_timestamp_without_timezone_offset() -> None:
    assert short_timestamp("2024-01-01T00:00:00") == "2024-01-01 00:00Z"


def test_short_timestamp_of_an_empty_input_is_empty() -> None:
    """No timestamp renders as nothing, not as a bare " Z".

    A file with no observation yet has ``last_seen == ""`` (``catalog_read`` coalesces the
    NULL), which partitions into empty halves and formatted into the marker alone.
    """
    assert short_timestamp("") == ""


# ---------------------------------------------------------------------------
# seasonal_locator
# ---------------------------------------------------------------------------


def test_seasonal_id_zero_pads_season_and_number() -> None:
    assert seasonal_locator(season=2, seasonal_number=11, letter="a") == "S02E11A"


def test_seasonal_id_uppercases_letter() -> None:
    assert seasonal_locator(season=1, seasonal_number=5, letter="b") == "S01E05B"


# ---------------------------------------------------------------------------
# micros_timestamp and average_rate: a source range's ends and rate (stage 4 spec, D12)
# ---------------------------------------------------------------------------


def test_micros_timestamp_keeps_the_seconds_of_a_range_end() -> None:
    assert micros_timestamp(TUESDAY_8PM + 30_999_999) == "2026-10-13 20:00:30Z"


def test_average_rate_is_the_bytes_over_the_range_length() -> None:
    assert average_rate(10 * 1024 * 1024, TUESDAY_8PM, TUESDAY_8PM + 10_240_000_000) == "1 KB/s"


def test_average_rate_of_a_range_without_bytes_is_empty() -> None:
    assert average_rate(0, TUESDAY_8PM, TUESDAY_8PM + 30_000_000) == ""


def test_average_rate_of_a_single_read_is_empty() -> None:
    assert average_rate(1024, TUESDAY_8PM, TUESDAY_8PM) == ""


def test_an_interval_end_shows_in_the_webui_format_and_in_a_datetime_local_input() -> None:
    at = datetime(2026, 10, 13, 20, 0, 30, 999_999, tzinfo=UTC)
    assert utc_timestamp(at) == "2026-10-13 20:00:30Z"
    assert input_timestamp(at) == "2026-10-13T20:00:30"
