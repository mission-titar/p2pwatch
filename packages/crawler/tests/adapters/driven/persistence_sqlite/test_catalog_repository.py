import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from catalog_matching.domain.engine import DecisionRecord, Explanation, MatchDecision
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.adapters.driven.persistence_sqlite.variants import content_hash, iso_to_micros
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, fold_raw_meta
from p2pwatch.domain.retraction import RETRACTED_TIER
from p2pwatch.ports.driven.catalog_repository import CatalogRepository, ReevalRow
from p2pwatch_testing.catalog_rows import count_observations, insert_file

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_HASH_B = "b" * 32
_KEY = FileKey(Network.ED2K, _HASH)
_NODE = "11111111-2222-3333-4444-555555555555"
_T0 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
_T0_ISO = "2026-06-11T12:00:00.000000+00:00"


def _observation(
    *,
    filename: str = "Keroro 062A.avi",
    size_bytes: int = 234567890,
    duration_seconds: int | None = None,
    bitrate_kbps: int | None = None,
) -> FileObservation:
    # raw_meta with a DUPLICATE, wire order, non-ASCII and the fold's native types.
    return FileObservation(
        file=_KEY,
        filename=filename,
        size_bytes=size_bytes,
        source_count=5,
        keyword="keroro",
        duration_seconds=duration_seconds,
        bitrate_kbps=bitrate_kbps,
        raw_meta=fold_raw_meta(
            (("0x0308", "0"), ("0x0308", "0"), ("0x0999", "mystère")), None, None, 2
        ),
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    yield catalog
    catalog.close()


@pytest.fixture
def repository(connection: sqlite3.Connection) -> SqliteCatalogRepository:
    return SqliteCatalogRepository(connection, _NODE)


def test_record_observation_round_trip(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    file_row = connection.execute("SELECT * FROM files").fetchone()
    assert file_row == (_KEY.file_id, "ed2k", _HASH, 234567890)
    variant = (
        _KEY.file_id,
        "Keroro 062A.avi",
        234567890,
        None,
        None,
        '[["0x0308", "0"], ["0x0308", "0"], ["0x0999", "mystère"], ["codec", null],'
        ' ["file_type", null], ["complete_source_count", 2]]',
        "keroro",
        _NODE,
    )
    row = connection.execute(
        "SELECT file_id, filename, size_bytes, duration_seconds, bitrate_kbps, raw_meta,"
        " keyword, node_id, content_hash FROM observation_variants"
    ).fetchone()
    assert row == (*variant, content_hash(*variant))
    observation = connection.execute("SELECT observed_at, source_count FROM observations")
    assert observation.fetchall() == [(iso_to_micros(_T0_ISO), 5)]


def test_raw_meta_preserves_order_duplicates_and_non_ascii(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    stored = connection.execute("SELECT raw_meta FROM observation_variants").fetchone()[0]
    assert "mystère" in stored  # ensure_ascii=False: the accent is stored AS IS
    assert json.loads(stored)[:3] == [["0x0308", "0"], ["0x0308", "0"], ["0x0999", "mystère"]]


def test_record_observation_twice_first_seen_wins_in_files(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    # Same hash, DIFFERENT size and name (hostile input, deviation 1 spec §5).
    repository.record_observation(_observation(filename="leurre.avi", size_bytes=999), _T0)
    assert connection.execute("SELECT size_bytes FROM files").fetchall() == [(234567890,)]
    observed_sizes = connection.execute(
        "SELECT size_bytes FROM observation_variants ORDER BY variant_id"
    ).fetchall()
    assert observed_sizes == [(234567890,), (999,)]  # the anomaly stays VISIBLE


def test_a_variant_seen_again_is_stored_once_with_both_timestamps(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    repository.record_observation(_observation(), _T0 + timedelta(minutes=1))
    assert connection.execute("SELECT count(*) FROM observation_variants").fetchone()[0] == 1
    assert count_observations(connection) == 2


def test_an_observation_equal_in_every_column_is_stored_once(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    repository.record_observation(_observation(), _T0)
    assert count_observations(connection) == 1


def test_record_observation_with_media_metadata(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(duration_seconds=1474, bitrate_kbps=1200), _T0)
    row = connection.execute(
        "SELECT duration_seconds, bitrate_kbps FROM observation_variants"
    ).fetchone()
    assert row == (1474, 1200)


def test_record_observation_is_one_transaction(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    # Failure injected on the last INSERT: a TEST trigger makes the observation fail.
    connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON observations"
        " WHEN NEW.source_count = 404"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    with pytest.raises(PersistenceError, match="injected failure"):
        repository.record_observation(dataclasses.replace(_observation(), source_count=404), _T0)
    # ATOMICITY: the file and its variant were rolled back with the transaction.
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM observation_variants").fetchone()[0] == 0
    # The repository stays USABLE: rollback done, connection out of transaction.
    assert not connection.in_transaction
    repository.record_observation(_observation(), _T0)
    assert count_observations(connection) == 1


def test_record_observation_rejects_non_canonical_hash(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    # INSERT OR IGNORE SILENTLY swallows a CHECK violation (documented SQLite
    # behavior): without Python validation BEFORE the transaction, a non-canonical hash
    # would only survive thanks to the foreign_keys pragma (opaque diagnostic), and a connection
    # without that pragma would commit an ORPHAN observation.
    upper = dataclasses.replace(_observation(), file=FileKey(Network.ED2K, _HASH.upper()))
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        repository.record_observation(upper, _T0)
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 0
    assert count_observations(connection) == 0


def test_rollback_on_non_sqlite_error_keeps_connection_usable(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    # An isolated surrogate makes the parameter BINDING fail (UnicodeEncodeError, which
    # is NOT a sqlite3.Error): without a rollback on BaseException, the connection
    # would stay in_transaction=True and every later call would fail permanently
    # ("cannot start a transaction within a transaction").
    with pytest.raises(UnicodeEncodeError):
        repository.record_observation(_observation(filename="a\ud800"), _T0)
    assert not connection.in_transaction
    repository.record_observation(_observation(), _T0)
    assert count_observations(connection) == 1


def test_outer_transaction_survives_record_observation_failure(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    # Nested-transaction contract: the repository's BEGIN fails ("cannot start a
    # transaction within a transaction") BEFORE the try → NO rollback is attempted,
    # the OUTER transaction and its pending rows SURVIVE.
    connection.execute("BEGIN")
    insert_file(connection, _HASH, 1)
    with pytest.raises(PersistenceError, match="cannot start a transaction within a transaction"):
        repository.record_observation(_observation(), _T0)
    assert connection.in_transaction  # the outer transaction is INTACT
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 1
    connection.execute("ROLLBACK")
    assert connection.execute("SELECT count(*) FROM files").fetchone()[0] == 0


def _decision() -> MatchDecision:
    return MatchDecision(
        target_id="062A",
        rule_name="exact_062a",
        tier="download",
        explanation=Explanation(
            target_id="062A",
            rules_fired=("exact_062a",),
            tokens_matched=("keroro",),
            coverage_values=(("titre", 0.91),),
        ),
    )


def test_record_decision_round_trip(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    repository.record_decision(_KEY, _decision(), _T0)
    row = connection.execute(
        "SELECT file_id, target_id, rule_name, tier, decided_at, node_id FROM match_decisions"
    ).fetchone()
    assert row == (_KEY.file_id, "062A", "exact_062a", "download", _T0_ISO, _NODE)


def test_explanation_is_never_persisted(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    repository.record_decision(_KEY, _decision(), _T0)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(match_decisions)").fetchall()
    }
    assert columns == {"id", "file_id", "target_id", "rule_name", "tier", "decided_at", "node_id"}


def test_record_decision_for_unknown_file_raises_persistence_error(
    repository: SqliteCatalogRepository,
) -> None:
    # FK violated (file never observed): sqlite3.IntegrityError WRAPPED, never bare.
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        repository.record_decision(FileKey(Network.ED2K, "0" * 32), _decision(), _T0)


def test_record_decision_rejects_non_canonical_hash(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    # Python validation BEFORE any transaction: an uppercase hash is rejected
    # with a clear message, no row is written.
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        repository.record_decision(FileKey(Network.ED2K, _HASH.upper()), _decision(), _T0)
    assert connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0


def test_repository_satisfies_the_port_structurally(
    repository: SqliteCatalogRepository,
) -> None:
    port: CatalogRepository = repository  # mypy proves structural satisfaction
    port.record_observation(_observation(), _T0)


def test_record_retraction_round_trip(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    repository.record_retraction(_KEY, "062A", _T0)
    row = connection.execute(
        "SELECT file_id, target_id, rule_name, tier, decided_at, node_id FROM match_decisions"
    ).fetchone()
    assert row == (_KEY.file_id, "062A", "", RETRACTED_TIER, _T0_ISO, _NODE)
    assert repository.latest_decisions(_KEY) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER)
    }


def test_record_retraction_rejects_non_canonical_hash(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        repository.record_retraction(FileKey(Network.ED2K, "NOTAHASH"), "062A", _T0)
    assert connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 0


def test_record_retraction_for_unknown_file_raises_persistence_error(
    repository: SqliteCatalogRepository,
) -> None:
    # FK violated (file never observed): mirrors record_decision's own guard.
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        repository.record_retraction(FileKey(Network.ED2K, "0" * 32), "062A", _T0)


def test_record_retraction_row_is_append_only(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    repository.record_observation(_observation(), _T0)
    repository.record_retraction(_KEY, "062A", _T0)
    with pytest.raises(sqlite3.IntegrityError, match="match_decisions is append-only"):
        connection.execute("UPDATE match_decisions SET tier = 'catalog'")
    with pytest.raises(sqlite3.IntegrityError, match="match_decisions is append-only"):
        connection.execute("DELETE FROM match_decisions")
    # The retracted row SURVIVED both attempts, untouched.
    assert repository.latest_decisions(_KEY) == {
        "062A": DecisionRecord(target_id="062A", rule_name="", tier=RETRACTED_TIER)
    }


def test_iter_reevaluation_rows_returns_the_latest_observation_per_hash(
    repository: SqliteCatalogRepository,
) -> None:
    # _HASH gets TWO observations a minute apart: only the LATEST must come back.
    # _HASH_B gets a single observation with media metadata present.
    repository.record_observation(_observation(filename="old.avi", size_bytes=100), _T0)
    repository.record_observation(
        _observation(filename="new.avi", size_bytes=200), _T0 + timedelta(minutes=1)
    )
    repository.record_observation(
        dataclasses.replace(
            _observation(
                filename="other.avi", size_bytes=300, duration_seconds=1234, bitrate_kbps=1500
            ),
            file=FileKey(Network.ED2K, _HASH_B),
        ),
        _T0,
    )
    rows = list(repository.iter_reevaluation_rows())
    assert rows == [
        ReevalRow(
            file=_KEY,
            filename="new.avi",
            size_bytes=200,
            duration_seconds=None,
            bitrate_kbps=None,
        ),
        ReevalRow(
            file=FileKey(Network.ED2K, _HASH_B),
            filename="other.avi",
            size_bytes=300,
            duration_seconds=1234,
            bitrate_kbps=1500,
        ),
    ]


def test_iter_reevaluation_rows_is_empty_with_an_empty_catalogue(
    repository: SqliteCatalogRepository,
) -> None:
    assert list(repository.iter_reevaluation_rows()) == []


def test_iter_reevaluation_rows_breaks_an_observed_at_tie_on_the_highest_variant(
    repository: SqliteCatalogRepository,
) -> None:
    # Both rows share observed_at, so the newer variant (higher variant_id) wins.
    repository.record_observation(_observation(filename="first.avi"), _T0)
    repository.record_observation(_observation(filename="second.avi"), _T0)
    assert [row.filename for row in repository.iter_reevaluation_rows()] == ["second.avi"]


def test_count_files_counts_catalogued_hashes_not_observations(
    repository: SqliteCatalogRepository,
) -> None:
    assert repository.count_files() == 0
    repository.record_observation(_observation(), _T0)
    repository.record_observation(_observation(), _T0)
    repository.record_observation(
        dataclasses.replace(_observation(), file=FileKey(Network.ED2K, _HASH_B)), _T0
    )
    assert repository.count_files() == 2


def test_iter_reevaluation_rows_skips_a_file_never_observed(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    insert_file(connection, _HASH, 1)
    assert list(repository.iter_reevaluation_rows()) == []


def test_last_observation_of_a_file_never_observed_is_none(
    repository: SqliteCatalogRepository, connection: sqlite3.Connection
) -> None:
    insert_file(connection, _HASH, 1)
    assert repository.latest_observation(_KEY) is None
