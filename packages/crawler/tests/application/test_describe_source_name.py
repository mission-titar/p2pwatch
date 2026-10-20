"""``DescribeSourceName``: a page of the sources that carried a name and its sharing periods
without a user hash over the requested interval."""

from datetime import UTC, datetime, timedelta
from typing import Any

from p2pwatch.application.describe_source_name import PAGE_SIZE, DescribeSourceName
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.interval import Interval
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey, SourceRole
from p2pwatch.domain.source_history import SourceHistory, SourceNameHistory, SourceNaming
from p2pwatch.ports.driven.source_reader import SourceReader
from p2pwatch.ports.driving.source_name_describer import SourceNameDescription
from p2pwatch_testing.application.fakes import FakeTime

_NOW = datetime(2026, 10, 14, 20, 0, 0, 654321, tzinfo=UTC)
_SECOND_NOW = _NOW.replace(microsecond=0)
_GAP = timedelta(seconds=90)
_SOURCE = SourceKey(Network.ED2K, "1f2e" * 8)
_NAMING = SourceNaming(_SOURCE, "AnimuseeFMR", _NOW, 1)


def _history(naming_count: int = 1) -> SourceNameHistory:
    return SourceNameHistory("AnimuseeFMR", (_NAMING,) * naming_count, (), {})


class _FakeSourceReader(SourceReader):
    """Reads ``source_name_history`` for any name, and keeps each call's arguments."""

    def __init__(self, source_name_history: SourceNameHistory | None) -> None:
        self._source_name_history = source_name_history
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read_source_name_history(
        self, source_name: str, **arguments: Any
    ) -> SourceNameHistory | None:
        self.calls.append((source_name, arguments))
        return self._source_name_history

    def read_source_history(self, source_id: bytes, **arguments: Any) -> SourceHistory | None:
        raise AssertionError("DescribeSourceName describes no source")

    def read_known_sources(self, **arguments: Any) -> tuple[KnownSource, ...]:
        raise AssertionError("DescribeSourceName lists no source")

    def read_source_count(self, **arguments: Any) -> int:
        raise AssertionError("DescribeSourceName counts no source")

    def read_sharing_periods(
        self, file: FileKey, window: PeriodWindow
    ) -> tuple[SharingPeriod, ...]:
        raise AssertionError("DescribeSourceName reads no file's periods")


def _describe(
    reader: SourceReader,
    *,
    page: int = 1,
    requested_since: datetime | None = None,
    requested_until: datetime | None = None,
) -> SourceNameDescription | None:
    describe_source_name = DescribeSourceName(
        source_reader=reader, wall_clock=FakeTime(_NOW).wall, source_period_gap=_GAP
    )
    return describe_source_name.describe_source_name(
        "AnimuseeFMR", page=page, requested_since=requested_since, requested_until=requested_until
    )


def test_a_name_never_recorded_has_no_description() -> None:
    assert _describe(_FakeSourceReader(None)) is None


def test_the_history_is_read_over_the_last_7_days_ending_now_to_the_second() -> None:
    reader = _FakeSourceReader(_history())

    description = _describe(reader)

    week = Interval(_SECOND_NOW - timedelta(days=7), _SECOND_NOW)
    assert description == SourceNameDescription(_history(), False, week, _SECOND_NOW)
    window = PeriodWindow(week.since, week.until, _GAP)
    assert reader.calls == [("AnimuseeFMR", {"limit": PAGE_SIZE, "offset": 0, "window": window})]


def test_the_periods_are_read_over_the_requested_interval_with_the_gap() -> None:
    reader = _FakeSourceReader(_history())
    since, until = datetime(2026, 10, 8, tzinfo=UTC), datetime(2026, 10, 11, tzinfo=UTC)

    description = _describe(reader, requested_since=since, requested_until=until)

    assert description is not None
    assert description.interval == Interval(since, until)
    assert reader.calls[0][1]["window"] == PeriodWindow(since, until, _GAP)


def test_a_page_starts_after_the_sources_of_the_pages_before_it() -> None:
    reader = _FakeSourceReader(_history())

    _describe(reader, page=3)

    assert reader.calls[0][1]["offset"] == 2 * PAGE_SIZE == 100


def test_only_a_full_page_of_sources_offers_a_next_one() -> None:
    full = _describe(_FakeSourceReader(_history(PAGE_SIZE)))
    short = _describe(_FakeSourceReader(_history(PAGE_SIZE - 1)))
    assert full is not None and full.has_next_page
    assert short is not None and not short.has_next_page


def test_every_period_read_is_described_on_every_page() -> None:
    period = SharingPeriod(
        FileKey(Network.ED2K, "a" * 32), None, "AnimuseeFMR", SourceRole.QUEUED,
        None, None, _NOW, _NOW, 0, "n1",
    )  # fmt: skip
    history = SourceNameHistory("AnimuseeFMR", (_NAMING,), (period,) * (PAGE_SIZE + 1), {})

    description = _describe(_FakeSourceReader(history), page=2)

    assert description is not None
    assert description.source_name_history == history
