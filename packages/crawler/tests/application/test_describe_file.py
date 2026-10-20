"""``DescribeFile``: a file's history and sharing periods over the requested interval, and why
its first decision holds against the current policy."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.engine import DecisionRecord, Explanation
from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.application.describe_file import DescribeFile
from p2pwatch.application.matching_read import MatchingExplainer
from p2pwatch.domain.catalog_entry import CatalogEntry
from p2pwatch.domain.file_history import DatedDecision, FileHistory
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.interval import Interval
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceRole
from p2pwatch.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.ports.driven.source_reader import SourceReader
from p2pwatch.ports.driving.file_describer import FileDescription
from p2pwatch_testing.application.fakes import FakeTime

_NOW = datetime(2026, 10, 14, 20, 0, 0, 654321, tzinfo=UTC)
_SECOND_NOW = _NOW.replace(microsecond=0)
_FILE = FileKey(Network.ED2K, "a" * 32)
_GAP = timedelta(seconds=90)
_OBSERVATION = FileObservation(
    ReportedFile(_FILE, "keroro_062a.avi", 100, 5, "keroro", 1300, 900, ()),
    _NOW - timedelta(hours=1),
)
_DECISION = DatedDecision(DecisionRecord("062A", "catalog", "catalog"), _NOW, "n1")
_HISTORY = FileHistory(
    _FILE, 100, (_OBSERVATION,), _OBSERVATION, (_DECISION,), ("Keroro 62a ITA.avi", "keroro.avi")
)
_PERIOD = SharingPeriod(_FILE, None, "Teammate", SourceRole.QUEUED, None, None, _NOW, _NOW, 0, "n1")
_TARGETS = parse_targets(
    yaml.safe_load(
        """\
episodes:
  - season: 2
    seasonal_number: 11
    absolute_number: 62
    segments:
      - letter: a
        title: "La Grenouille Cosmique"
"""
    )
)
_MATCHER = parse_matcher_config(
    {
        "tokens": {"keroro": {"keyword": "keroro"}, "ita": {"regex": r"\bITA\b"}},
        "vetoes": ["ita"],
        "rules": [
            {"name": "catalog", "tier": "catalog", "scope": "unattributed", "any": ["keroro"]}
        ],
    }
)


class _FakeCatalogFileReader(CatalogFileReader):
    """Reads ``file_history`` for any file id, and keeps each call's arguments."""

    def __init__(self, file_history: FileHistory | None) -> None:
        self._file_history = file_history
        self.calls: list[tuple[bytes, dict[str, Any]]] = []

    def read_file_history(self, file_id: bytes, **arguments: Any) -> FileHistory | None:
        self.calls.append((file_id, arguments))
        return self._file_history

    def read_catalog_entries(self, **arguments: Any) -> tuple[CatalogEntry, ...]:
        raise AssertionError("DescribeFile lists no file")

    def read_matched_and_total_file_counts(self, **arguments: Any) -> tuple[int, int]:
        raise AssertionError("DescribeFile counts no file")

    def read_file_count_by_tier(self, **arguments: Any) -> Mapping[str, int]:
        raise AssertionError("DescribeFile counts no tier")


class _FakeSourceReader(SourceReader):
    def __init__(self) -> None:
        self.calls: list[tuple[FileKey, PeriodWindow]] = []

    def read_known_sources(self, **arguments: Any) -> tuple[KnownSource, ...]:
        raise AssertionError("DescribeFile lists no source")

    def read_source_count(self, **arguments: Any) -> int:
        raise AssertionError("DescribeFile counts no source")

    def read_sharing_periods(
        self, file: FileKey, window: PeriodWindow
    ) -> tuple[SharingPeriod, ...]:
        self.calls.append((file, window))
        return (_PERIOD,)


def _describe(
    catalog_file_reader: CatalogFileReader,
    source_reader: SourceReader | None = None,
    *,
    requested_since: datetime | None = None,
    requested_until: datetime | None = None,
    matcher_config: MatcherConfig = _MATCHER,
) -> FileDescription | None:
    describe_file = DescribeFile(
        catalog_file_reader=catalog_file_reader,
        source_reader=source_reader or _FakeSourceReader(),
        explainer=MatchingExplainer(matcher_config=matcher_config, targets=_TARGETS),
        wall_clock=FakeTime(_NOW).wall,
        source_period_gap=_GAP,
    )
    return describe_file.describe_file(
        b"\x01" * 16, requested_since=requested_since, requested_until=requested_until
    )


def test_a_file_the_catalog_does_not_hold_has_no_description() -> None:
    assert _describe(_FakeCatalogFileReader(None)) is None


def test_the_history_is_read_over_the_last_7_days_ending_now_to_the_second() -> None:
    reader, source_reader = _FakeCatalogFileReader(_HISTORY), _FakeSourceReader()
    description = _describe(reader, source_reader)
    week = Interval(_SECOND_NOW - timedelta(days=7), _SECOND_NOW)
    assert reader.calls == [(b"\x01" * 16, {"since": week.since, "until": week.until})]
    assert source_reader.calls == [(_FILE, PeriodWindow(week.since, week.until, _GAP))]
    assert description is not None
    assert (description.interval, description.now) == (week, _SECOND_NOW)


def test_the_sharing_periods_are_read_over_the_requested_interval_with_the_gap() -> None:
    since, until = datetime(2026, 10, 10, tzinfo=UTC), datetime(2026, 10, 12, tzinfo=UTC)
    reader, source_reader = _FakeCatalogFileReader(_HISTORY), _FakeSourceReader()
    description = _describe(reader, source_reader, requested_since=since, requested_until=until)
    assert reader.calls == [(b"\x01" * 16, {"since": since, "until": until})]
    assert source_reader.calls == [(_FILE, PeriodWindow(since, until, _GAP))]
    assert description is not None
    assert (description.file_history, description.sharing_periods) == (_HISTORY, (_PERIOD,))
    assert description.interval == Interval(since, until)


def test_the_first_decision_is_explained_over_every_known_filename() -> None:
    description = _describe(_FakeCatalogFileReader(_HISTORY))
    assert description is not None
    assert description.explanation == Explanation(
        target_id="062A",
        rules_fired=("catalog",),
        tokens_matched=("ita", "keroro"),
        coverage_values=(),
        vetoes_fired=("ita",),
    )


def test_the_explanation_judges_the_latest_observations_duration_and_bitrate() -> None:
    # Each token holds only on the latest observation's exact value (1300 s, 900 kbps).
    media_tokens = {
        "long": {"attr_between": "duration_seconds", "min": 1300.0, "max": 1300.0},
        "dense": {"attr_between": "bitrate_kbps", "min": 900.0, "max": 900.0},
    }
    matcher_config = parse_matcher_config(
        {
            "tokens": {"keroro": {"keyword": "keroro"}, **media_tokens},
            "rules": [
                {"name": "media", "tier": "catalog", "scope": "unattributed", "all": ["long"]}
            ],
        }
    )
    description = _describe(_FakeCatalogFileReader(_HISTORY), matcher_config=matcher_config)
    assert description is not None
    assert description.explanation is not None
    assert description.explanation.tokens_matched == ("dense", "keroro", "long")


def test_a_file_without_a_decision_or_never_seen_has_no_explanation() -> None:
    for file_history in (
        FileHistory(_FILE, 100, (_OBSERVATION,), _OBSERVATION, (), ("keroro.avi",)),
        FileHistory(_FILE, 100, (), None, (_DECISION,), ()),
    ):
        description = _describe(_FakeCatalogFileReader(file_history))
        assert description is not None
        assert description.explanation is None
