"""Tests for the re-evaluation use-case ``reevaluate_catalog`` (spec §7, plan Task 5).

Real engine + real SQLite catalog repo (same convention as ``test_decisions.py``: "real
repos on tmp_path"); only ``wake_hub``/``telemetry``/``wall_clock`` are fakes (``RecordingWakeHub``/
``RecordingTelemetry``/``FakeWallClock``). Each hash under test is seeded via
``catalog.record_observation`` first so it shows up in ``iter_reevaluation_rows`` (the source the
re-evaluation iterates).
"""

import sqlite3
from datetime import timedelta

import pytest

from catalog_matching.domain.engine import (
    DecisionRecord,
    Explanation,
    MatchDecision,
    MatchingEngine,
)
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.application import reevaluate_catalog as reevaluate_module
from p2pwatch.application.reevaluate_catalog import ReevaluationSummary, reevaluate_catalog
from p2pwatch.application.run_download_cycle import DOWNLOAD_WAKE_SUBJECT
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.retraction import RETRACTED_TIER
from p2pwatch_testing.application.fakes import (
    FakeLogger,
    FakeTime,
    FakeWallClock,
    LoggedLine,
    RecordingTelemetry,
    RecordingWakeHub,
)
from p2pwatch_testing.catalog_rows import decision_tiers

_HASH_DL = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_CAT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_HASH_MULTI = "dddddddddddddddddddddddddddddddd"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
_CAT_NAME = "keroro something.avi"
_MULTI_NAME = "Keroro 062 teletoon.avi"  # → 062A + 062B download (post-fan-out)


def _reported_file(ed2k_hash: str, filename: str) -> ReportedFile:
    return ReportedFile(
        file=FileKey(Network.ED2K, ed2k_hash),
        filename=filename,
        size_bytes=234_000_000,
        source_count=3,
        keyword="keroro",
    )


def _legacy_row(target_id: str, rule_name: str, tier: str) -> MatchDecision:
    return MatchDecision(
        target_id=target_id,
        rule_name=rule_name,
        tier=tier,
        explanation=Explanation(
            target_id=target_id, rules_fired=(), tokens_matched=(), coverage_values=()
        ),
    )


@pytest.mark.asyncio
async def test_two_changed_rows_are_all_evaluated_and_written(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # Never decided: both will change.
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now())
    )
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now())
    )
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    summary = await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        logger=FakeLogger(),
    )
    assert summary == ReevaluationSummary(files_evaluated=2, rows_written=2)
    tiers = dict(decision_tiers(catalog_connection))
    assert tiers == {_HASH_DL: "download", _HASH_CAT: "catalog"}
    decided_at = catalog_connection.execute("SELECT DISTINCT decided_at FROM match_decisions")
    assert decided_at.fetchall() == [(utc_iso(wall_clock.now()),)]
    assert len(telemetry.events) == 2
    # Iteration is ORDER BY native_id: "31d6..." sorts before "aaaa..." (ASCII '3' < 'a').
    assert wake_hub.woken_subjects == [DOWNLOAD_WAKE_SUBJECT]


@pytest.mark.asyncio
async def test_unchanged_row_is_evaluated_but_not_written(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now())
    )
    candidate = _reported_file(_HASH_CAT, _CAT_NAME).to_candidate()
    decisions = engine.evaluate_file((candidate,))
    assert decisions  # non-empty
    # pre-seed the "already correct" verdict
    catalog.record_decision(FileKey(Network.ED2K, _HASH_CAT), decisions[0], wall_clock.now())
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    summary = await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        logger=FakeLogger(),
    )
    assert summary == ReevaluationSummary(files_evaluated=1, rows_written=0)
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    assert telemetry.events == []
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_repository_error_on_one_row_is_absorbed_and_sweep_continues(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now())
    )
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now())
    )
    logger = FakeLogger()
    # TEST trigger: makes the match_decisions INSERT fail for ONE hash only -> that row's
    # helper call raises RepositoryError, the other row must still be processed.
    catalog_connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON match_decisions"
        f" WHEN NEW.file_id = x'{FileKey(Network.ED2K, _HASH_DL).file_id.hex()}'"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    summary = await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        logger=logger,
    )
    assert summary == ReevaluationSummary(files_evaluated=2, rows_written=1)
    assert decision_tiers(catalog_connection) == [(_HASH_CAT, "catalog")]
    assert catalog.latest_decisions(FileKey(Network.ED2K, _HASH_DL)) == {}
    assert logger.lines == [
        LoggedLine(
            "error",
            f"persistence failed on file=ed2k:{_HASH_DL} (injected failure):"
            " re-evaluation skipped, sweep continues",
        )
    ]


@pytest.mark.asyncio
async def test_empty_catalogue_yields_zero_summary(
    catalog: SqliteCatalogRepository, engine: MatchingEngine, wall_clock: FakeWallClock
) -> None:
    telemetry = RecordingTelemetry()
    wake_hub = RecordingWakeHub()
    summary = await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        logger=FakeLogger(),
    )
    assert summary == ReevaluationSummary(files_evaluated=0, rows_written=0)
    assert telemetry.events == []
    assert wake_hub.woken_subjects == []


@pytest.mark.asyncio
async def test_backfill_retracts_a_legacy_arbitrary_target_row(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # §10: an old "unidentified" row under an arbitrary target_id (001A/catalog) is retracted
    # by the set-diff when the file becomes identified (062A + 062B) on the re-evaluation pass.
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), wall_clock.now())
    )
    catalog.record_decision(
        FileKey(Network.ED2K, _HASH_MULTI),
        _legacy_row("001A", "keroro_large", "catalog"),
        wall_clock.now(),
    )
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    summary = await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        logger=FakeLogger(),
    )
    assert summary == ReevaluationSummary(
        files_evaluated=1, rows_written=3
    )  # 062A + 062B + retract 001A
    assert catalog.latest_decisions(FileKey(Network.ED2K, _HASH_MULTI)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="numero_nu_confirmed", tier="download"),
        "062B": DecisionRecord(target_id="062B", rule_name="numero_nu_confirmed", tier="download"),
        "001A": DecisionRecord(target_id="001A", rule_name="", tier=RETRACTED_TIER),
    }


@pytest.mark.asyncio
async def test_backfill_ignores_the_legacy_empty_sentinel(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
) -> None:
    # §10: the old whole-file retraction sentinel (target_id="") is invisible to the set-diff.
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, _MULTI_NAME), wall_clock.now())
    )
    catalog.record_decision(
        FileKey(Network.ED2K, _HASH_MULTI), _legacy_row("", "", RETRACTED_TIER), wall_clock.now()
    )
    telemetry, wake_hub = RecordingTelemetry(), RecordingWakeHub()
    summary = await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=wake_hub,
        telemetry=telemetry,
        wall_clock=wall_clock,
        logger=FakeLogger(),
    )
    assert summary == ReevaluationSummary(
        files_evaluated=1, rows_written=2
    )  # only 062A + 062B; "" untouched
    assert set(catalog.latest_decisions(FileKey(Network.ED2K, _HASH_MULTI))) == {"062A", "062B"}
    assert (
        catalog_connection.execute(
            "SELECT count(*) FROM match_decisions WHERE target_id = ''"
        ).fetchone()[0]
        == 1
    )


@pytest.mark.asyncio
async def test_backfill_judges_a_hash_on_all_its_names_not_only_the_latest(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    fake_time: FakeTime,
    wall_clock: FakeWallClock,
) -> None:
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now())
    )
    fake_time.advance(timedelta(minutes=1))  # the latest name matches nothing
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_DL, "random.txt"), wall_clock.now())
    )
    summary = await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=RecordingWakeHub(),
        telemetry=RecordingTelemetry(),
        wall_clock=wall_clock,
        logger=FakeLogger(),
    )
    assert summary == ReevaluationSummary(files_evaluated=1, rows_written=1)
    assert catalog.latest_decisions(FileKey(Network.ED2K, _HASH_DL)) == {
        "062A": DecisionRecord(target_id="062A", rule_name="id_segment_exact", tier="download")
    }


@pytest.mark.asyncio
async def test_progress_is_logged_at_each_multiple_of_the_cadence_only(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    wall_clock: FakeWallClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reevaluate_module, "_PROGRESS_EVERY", 2)
    logger = FakeLogger()
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_DL, _DL_NAME), wall_clock.now())
    )
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_CAT, _CAT_NAME), wall_clock.now())
    )
    catalog.record_observation(
        FileObservation(_reported_file(_HASH_MULTI, "random.txt"), wall_clock.now())
    )
    await reevaluate_catalog(
        catalog=catalog,
        engine=engine,
        wake_hub=RecordingWakeHub(),
        telemetry=RecordingTelemetry(),
        wall_clock=wall_clock,
        logger=logger,
    )
    assert logger.lines == [
        LoggedLine("info", "catalogue re-evaluation: 2/3 files, 2 rows written")
    ]


def test_progress_cadence_is_every_200_files() -> None:
    assert reevaluate_module._PROGRESS_EVERY == 200
