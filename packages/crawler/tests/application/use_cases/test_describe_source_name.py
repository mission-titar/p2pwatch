"""``DescribeSourceName``: a page of the sources that carried a name and its sharing periods
without a user hash over the requested interval."""

from datetime import UTC, datetime, timedelta

from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.application.ports.driving.source_name_describer import SourceNameDescription
from p2pwatch.application.use_cases.describe_source_name import DescribeSourceName
from p2pwatch.application.use_cases.paging import PAGE_SIZE
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.interval import Interval
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey, SourceRole
from p2pwatch.domain.source_history import SourceNameHistory, SourceNaming
from tests.fakes.adapters.driven.fake_source_reader import FakeSourceReader
from tests.fakes.adapters.driven.fake_time import FakeTime

_NOW = datetime(2026, 10, 14, 20, 0, 0, 654321, tzinfo=UTC)
_SECOND_NOW = _NOW.replace(microsecond=0)
_GAP = timedelta(seconds=90)
_SOURCE = SourceKey(network=Network.ED2K, native_id="1f2e" * 8)
_NAMING = SourceNaming(source=_SOURCE, source_name="AnimuseeFMR", latest_seen_at=_NOW, file_count=1)


def _history(naming_count: int = 1) -> SourceNameHistory:
    return SourceNameHistory(
        source_name="AnimuseeFMR",
        source_namings=(_NAMING,) * naming_count,
        sharing_periods=(),
        best_filename_by_file={},
    )


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
    assert _describe(FakeSourceReader()) is None


def test_the_history_is_read_over_the_last_7_days_ending_now_to_the_second() -> None:
    reader = FakeSourceReader(source_name_history=_history())

    description = _describe(reader)

    week = Interval(since=_SECOND_NOW - timedelta(days=7), until=_SECOND_NOW)
    assert description == SourceNameDescription(_history(), False, week, _SECOND_NOW)
    window = PeriodWindow(since=week.since, until=week.until, gap=_GAP)
    assert reader.calls == [
        (
            "read_source_name_history",
            {"source_name": "AnimuseeFMR", "limit": PAGE_SIZE, "offset": 0, "window": window},
        )
    ]


def test_the_periods_are_read_over_the_requested_interval_with_the_gap() -> None:
    reader = FakeSourceReader(source_name_history=_history())
    since, until = datetime(2026, 10, 8, tzinfo=UTC), datetime(2026, 10, 11, tzinfo=UTC)

    description = _describe(reader, requested_since=since, requested_until=until)

    assert description is not None
    assert description.interval == Interval(since=since, until=until)
    assert reader.calls[0][1]["window"] == PeriodWindow(since=since, until=until, gap=_GAP)


def test_a_request_past_7_days_reads_the_7_ending_at_its_until() -> None:
    reader = FakeSourceReader(source_name_history=_history())
    since, until = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
    week = Interval(since=until - timedelta(days=7), until=until, clamped=True)

    description = _describe(reader, requested_since=since, requested_until=until)

    assert description is not None and description.interval == week
    assert reader.calls[0][1]["window"] == PeriodWindow(since=week.since, until=until, gap=_GAP)


def test_an_inverted_request_reads_the_7_days_ending_at_its_until() -> None:
    reader = FakeSourceReader(source_name_history=_history())
    since, until = datetime(2026, 10, 12, tzinfo=UTC), datetime(2026, 10, 10, tzinfo=UTC)
    week = Interval(since=until - timedelta(days=7), until=until)

    description = _describe(reader, requested_since=since, requested_until=until)

    assert description is not None and description.interval == week
    assert reader.calls[0][1]["window"] == PeriodWindow(since=week.since, until=until, gap=_GAP)


def test_a_page_starts_after_the_sources_of_the_pages_before_it() -> None:
    reader = FakeSourceReader(source_name_history=_history())

    _describe(reader, page=3)

    assert reader.calls[0][1]["offset"] == 2 * PAGE_SIZE == 100


def test_only_a_full_page_of_sources_offers_a_next_one() -> None:
    full = _describe(FakeSourceReader(source_name_history=_history(PAGE_SIZE)))
    short = _describe(FakeSourceReader(source_name_history=_history(PAGE_SIZE - 1)))
    assert full is not None and full.has_next_page
    assert short is not None and not short.has_next_page


def test_every_period_read_is_described_on_every_page() -> None:
    period = SharingPeriod(
        file=FileKey(network=Network.ED2K, native_id="a" * 32),
        source=None,
        source_name="AnimuseeFMR",
        role=SourceRole.QUEUED,
        contact_point=None,
        connectable=None,
        first_seen_at=_NOW,
        last_seen_at=_NOW,
        received_bytes=0,
        node_id=NodeId("n1"),
    )
    history = SourceNameHistory(
        source_name="AnimuseeFMR",
        source_namings=(_NAMING,),
        sharing_periods=(period,) * (PAGE_SIZE + 1),
        best_filename_by_file={},
    )

    description = _describe(FakeSourceReader(source_name_history=history), page=2)

    assert description is not None
    assert description.source_name_history == history
