"""``DescribeFile``: a file's history and sharing periods over the requested interval, and why
its first decision holds against the current policy."""

from datetime import UTC, datetime, timedelta

import yaml

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord, Explanation, MatchingEngine
from catalog_matching.domain.identifiers import TargetId
from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.application.ports.driving.file_describer import FileDescription
from p2pwatch.application.use_cases.describe_file import DescribeFile
from p2pwatch.domain.file_history import FileHistory
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision
from p2pwatch.domain.identifiers import FileId, Keyword, NodeId
from p2pwatch.domain.interval import Interval
from p2pwatch.domain.matching_read import MatchingExplainer
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceRole
from tests.fakes.adapters.driven.fake_catalog_file_reader import FakeCatalogFileReader
from tests.fakes.adapters.driven.fake_source_reader import FakeSourceReader
from tests.fakes.adapters.driven.fake_time import FakeTime

_NOW = datetime(2026, 10, 14, 20, 0, 0, 654321, tzinfo=UTC)
_SECOND_NOW = _NOW.replace(microsecond=0)
_FILE = FileKey(network=Network.ED2K, native_id="a" * 32)
_GAP = timedelta(seconds=90)
_OBSERVATION = FileObservation(
    reported_file=ReportedFile(
        file=_FILE,
        filename="keroro_062a.avi",
        size_bytes=100,
        source_count=5,
        keyword=Keyword("keroro"),
        duration_seconds=1300,
        bitrate_kbps=900,
        raw_metadata=(),
    ),
    observed_at=_NOW - timedelta(hours=1),
    node_id=NodeId("n1"),
)
_DECISION = DatedDecision(
    file=_FILE,
    decision=DecisionRecord(
        target_id=TargetId("062A"), rule_name="catalog", tier=DecisionTier.CATALOG
    ),
    decided_at=_NOW,
    node_id=NodeId("n1"),
)
_HISTORY = FileHistory(
    file=_FILE,
    size_bytes=100,
    observations=(_OBSERVATION,),
    latest_observation=_OBSERVATION,
    decisions=(_DECISION,),
    known_filenames=("Keroro 62a ITA.avi", "keroro.avi"),
)
_PERIOD = SharingPeriod(
    file=_FILE,
    source=None,
    source_name="Teammate",
    role=SourceRole.QUEUED,
    contact_point=None,
    connectable=None,
    first_seen_at=_NOW,
    last_seen_at=_NOW,
    received_bytes=0,
    node_id=NodeId("n1"),
)
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

_MAX_FILENAME_LENGTH = 4096
_MATCHER = parse_matcher_config(
    {
        "tokens": {"keroro": {"keyword": "keroro"}, "ita": {"regex": r"\bITA\b"}},
        "vetoes": ["ita"],
        "rules": [
            {"name": "catalog", "tier": "catalog", "scope": "unattributed", "any": ["keroro"]}
        ],
    }
)


def _readers() -> tuple[FakeCatalogFileReader, FakeSourceReader]:
    """A catalog holding ``_HISTORY``, and the file's one sharing period."""
    catalog_file_reader = FakeCatalogFileReader(file_history=_HISTORY)
    return catalog_file_reader, FakeSourceReader(sharing_periods=(_PERIOD,))


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
        source_reader=source_reader or FakeSourceReader(),
        explainer=MatchingExplainer(
            engine=MatchingEngine(
                matcher_config, targets=_TARGETS, max_filename_length=_MAX_FILENAME_LENGTH
            )
        ),
        wall_clock=FakeTime(_NOW).wall,
        source_period_gap=_GAP,
    )
    return describe_file.describe_file(
        FileId(b"\x01" * 16), requested_since=requested_since, requested_until=requested_until
    )


def test_a_file_the_catalog_does_not_hold_has_no_description() -> None:
    assert _describe(FakeCatalogFileReader()) is None


def test_the_history_is_read_over_the_last_7_days_ending_now_to_the_second() -> None:
    reader, source_reader = _readers()
    description = _describe(reader, source_reader)
    week = Interval(since=_SECOND_NOW - timedelta(days=7), until=_SECOND_NOW)
    assert reader.calls == [
        ("read_file_history", {"file_id": b"\x01" * 16, "since": week.since, "until": week.until})
    ]
    assert source_reader.calls == [
        (
            "read_sharing_periods",
            {"file": _FILE, "window": PeriodWindow(since=week.since, until=week.until, gap=_GAP)},
        )
    ]
    assert description is not None
    assert (description.interval, description.now) == (week, _SECOND_NOW)


def test_the_sharing_periods_are_read_over_the_requested_interval_with_the_gap() -> None:
    since, until = datetime(2026, 10, 10, tzinfo=UTC), datetime(2026, 10, 12, tzinfo=UTC)
    reader, source_reader = _readers()
    description = _describe(reader, source_reader, requested_since=since, requested_until=until)
    assert reader.calls == [
        ("read_file_history", {"file_id": b"\x01" * 16, "since": since, "until": until})
    ]
    assert source_reader.calls == [
        (
            "read_sharing_periods",
            {"file": _FILE, "window": PeriodWindow(since=since, until=until, gap=_GAP)},
        )
    ]
    assert description is not None
    assert (description.file_history, description.sharing_periods) == (_HISTORY, (_PERIOD,))
    assert description.interval == Interval(since=since, until=until)


def test_a_request_past_7_days_reads_the_7_ending_at_its_until() -> None:
    since, until = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
    week = Interval(since=until - timedelta(days=7), until=until, clamped=True)
    reader, source_reader = _readers()
    description = _describe(reader, source_reader, requested_since=since, requested_until=until)
    assert reader.calls == [
        ("read_file_history", {"file_id": b"\x01" * 16, "since": week.since, "until": until})
    ]
    assert source_reader.calls == [
        (
            "read_sharing_periods",
            {"file": _FILE, "window": PeriodWindow(since=week.since, until=until, gap=_GAP)},
        )
    ]
    assert description is not None and description.interval == week


def test_an_inverted_request_reads_the_7_days_ending_at_its_until() -> None:
    since, until = datetime(2026, 10, 12, tzinfo=UTC), datetime(2026, 10, 10, tzinfo=UTC)
    week = Interval(since=until - timedelta(days=7), until=until)
    reader, source_reader = _readers()
    description = _describe(reader, source_reader, requested_since=since, requested_until=until)
    assert reader.calls == [
        ("read_file_history", {"file_id": b"\x01" * 16, "since": week.since, "until": until})
    ]
    assert source_reader.calls == [
        (
            "read_sharing_periods",
            {"file": _FILE, "window": PeriodWindow(since=week.since, until=until, gap=_GAP)},
        )
    ]
    assert description is not None and description.interval == week


def test_the_first_decision_is_explained_over_every_known_filename() -> None:
    description = _describe(FakeCatalogFileReader(file_history=_HISTORY))
    assert description is not None
    assert description.explanation == Explanation(
        target_id=TargetId("062A"),
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
    description = _describe(
        FakeCatalogFileReader(file_history=_HISTORY), matcher_config=matcher_config
    )
    assert description is not None
    assert description.explanation is not None
    assert description.explanation.tokens_matched == ("dense", "keroro", "long")


def test_a_file_without_a_decision_or_never_seen_has_no_explanation() -> None:
    for file_history in (
        FileHistory(
            file=_FILE,
            size_bytes=100,
            observations=(_OBSERVATION,),
            latest_observation=_OBSERVATION,
            decisions=(),
            known_filenames=("keroro.avi",),
        ),
        FileHistory(
            file=_FILE,
            size_bytes=100,
            observations=(),
            latest_observation=None,
            decisions=(_DECISION,),
            known_filenames=(),
        ),
    ):
        description = _describe(FakeCatalogFileReader(file_history=file_history))
        assert description is not None
        assert description.explanation is None
