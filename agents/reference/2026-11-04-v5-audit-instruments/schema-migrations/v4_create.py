"""With v4.1.0's code, creates catalog.db and local.db as a v4.1.0 node does, plus edge-case copies.

Usage: uv run python v4_create.py <out_dir> [<bulk_observations>]
Writes <out_dir>/base/{catalog,local}.db, <out_dir>/edge-<case>/{catalog,local}.db, expected.json.
"""

import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from catalog_matching.engine import Explanation, MatchDecision
from mulewatch.adapters.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from mulewatch.adapters.persistence_sqlite.connection import open_catalog, open_local
from mulewatch.adapters.persistence_sqlite.download_repository import SqliteDownloadRepository
from mulewatch.adapters.persistence_sqlite.local_state_repository import (
    SqliteLocalStateRepository,
)
from mulewatch.adapters.persistence_sqlite.scheduler_state_repository import (
    SqliteSchedulerStateRepository,
)
from mulewatch.domain.download.states import DownloadState
from mulewatch.domain.observation import FileObservation
from mulewatch.ports.scheduler_state_repository import ChannelBackoff


class StepClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def step(self, **delta: float) -> None:
        self.now += timedelta(**delta)


H1 = "0123456789abcdef0123456789abcdef"
H2 = "fedcba9876543210fedcba9876543210"
H3 = "00000000000000000000000000000001"
H4 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def explanation(target_id: str) -> Explanation:
    fields = Explanation.__dataclass_fields__
    values: dict[str, object] = {"target_id": target_id}
    for name in fields:
        if name != "target_id":
            values[name] = ()
    return Explanation(**values)  # type: ignore[arg-type]


def make_base(directory: Path) -> dict[str, object]:
    directory.mkdir(parents=True)
    clock = StepClock(datetime(2026, 7, 4, 4, 30, 19, 228441, tzinfo=UTC))
    local = open_local(directory / "local.db")
    local_state = SqliteLocalStateRepository(local, clock=clock)
    node_id = local_state.node_id()
    local_state.set_last_backfill_policy("ab" * 32)
    catalog = open_catalog(directory / "catalog.db")
    repository = SqliteCatalogRepository(catalog, node_id, clock=clock)
    observations = [
        # Full metadata, media.* names, a non-ASCII filename.
        FileObservation(
            ed2k_hash=H1, filename="Keroro - 01 - Été.avi", size_bytes=367001600,
            source_count=12, complete_source_count=3, keyword="keroro",
            media_length_sec=1320, bitrate_kbps=4498, codec="xvid", file_type="Video",
            raw_meta=(("0x0308", "0"), ("media.title", "Keroro 01"), ("media.artist", "x"),
                      ("0xd3", "1320")),
        ),
        # Same file, other size: folds into the same variant (size lives in files).
        FileObservation(
            ed2k_hash=H1, filename="Keroro - 01 - Été.avi", size_bytes=367001601,
            source_count=12, complete_source_count=3, keyword="keroro",
            media_length_sec=1320, bitrate_kbps=4498, codec="xvid", file_type="Video",
            raw_meta=(("0x0308", "0"), ("media.title", "Keroro 01"), ("media.artist", "x"),
                      ("0xd3", "1320")),
        ),
        # No metadata at all.
        FileObservation(
            ed2k_hash=H2, filename="titar.mkv", size_bytes=0, source_count=0,
            complete_source_count=0, keyword="titar",
        ),
        # A repeated name and a 'media' name beside 'media.*': what v4 keeps that the fold loses.
        FileObservation(
            ed2k_hash=H3, filename="dup names", size_bytes=10, source_count=1,
            complete_source_count=1, keyword="keroro", media_length_sec=0, bitrate_kbps=0,
            raw_meta=(("k", "first"), ("k", "second"), ("media", "flat"), ("media.title", "t")),
        ),
    ]
    for observation in observations:
        repository.record_observation(observation)
        clock.step(seconds=1)
    # The same observation twice at the same instant: 0007 keeps one.
    repository.record_observation(observations[2])
    repository.record_observation(observations[2])
    clock.step(days=1)
    repository.record_observation(observations[2])
    repository.record_decision(H1, MatchDecision("k01a", "rule_a", "download", explanation("k01a")))
    repository.record_decision(H1, MatchDecision("k01b", "rule_b", "notify", explanation("k01b")))
    repository.record_retraction(H1, "k01b")
    repository.record_decision(H2, MatchDecision("", "", "catalog", explanation("")))
    clock.step(seconds=1)
    downloads = SqliteDownloadRepository(local, clock=clock)
    downloads.record_queued(H1, "k01a", 367001600)
    downloads.record_queued(H2, "k02a", 5)
    downloads.set_state(H2, DownloadState.DOWNLOADING)
    clock.step(seconds=1)
    downloads.set_state(H1, DownloadState.COMPLETED)
    downloads.mark_seen([H2])
    scheduler = SqliteSchedulerStateRepository(local)
    scheduler.write_cycle_state(7, clock())
    scheduler.save_channel_backoff({"amuled:global": ChannelBackoff(attempts=2, retry_after="2026-07-05T00:00:00.000000+00:00")})
    catalog.close()
    local.close()
    return {"node_id": node_id}


def bulk(directory: Path, count: int, node_id: str) -> None:
    """Rows shaped as v4 writes them, inserted in bulk for the interruption test."""
    connection = sqlite3.connect(directory / "catalog.db")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    with connection:
        hashes = [f"{n:032x}" for n in range(1000, 1200)]
        connection.executemany(
            "INSERT OR IGNORE INTO files (ed2k_hash, size_bytes, aich_hash) VALUES (?, ?, NULL)",
            [(h, 1000) for h in hashes],
        )
        rows = (
            (
                hashes[n % 200], f"name {n % 997}.avi", 1000, n % 13, n % 3, n % 1400, n % 5000,
                None, "Video", json.dumps([["0x0308", str(n % 7)]]), "keroro",
                (start + timedelta(microseconds=n * 1_000_003)).isoformat(timespec="microseconds"),
                node_id,
            )
            for n in range(count)
        )
        connection.executemany(
            "INSERT INTO file_observations (ed2k_hash, filename, size_bytes, source_count,"
            " complete_source_count, media_length_sec, bitrate_kbps, codec, file_type, raw_meta,"
            " keyword, observed_at, node_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    connection.close()


CATALOG_EDGES = {
    "negative-source-count": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, raw_meta, keyword, observed_at, node_id) VALUES"
    f" ('{H2}', 'x', 0, -1, 0, '[]', 'k', '2026-07-04T00:00:00.000000+00:00', 'n')",
    "real-duration": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, media_length_sec, raw_meta, keyword, observed_at,"
    f" node_id) VALUES ('{H2}', 'x', 0, 1, 0, 12.5, '[]', 'k',"
    " '2026-07-04T00:00:00.000000+00:00', 'n')",
    "negative-bitrate": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, bitrate_kbps, raw_meta, keyword, observed_at,"
    f" node_id) VALUES ('{H2}', 'x', 0, 1, 0, -5, '[]', 'k',"
    " '2026-07-04T00:00:00.000000+00:00', 'n')",
    "naive-observed-at": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, raw_meta, keyword, observed_at, node_id) VALUES"
    f" ('{H2}', 'x', 0, 1, 0, '[]', 'k', '2026-07-04T00:00:00.000000', 'n')",
    "offset-observed-at": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, raw_meta, keyword, observed_at, node_id) VALUES"
    f" ('{H2}', 'x', 0, 1, 0, '[]', 'k', '2026-07-04T02:00:00.000000+02:00', 'n')",
    "raw-meta-object": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, raw_meta, keyword, observed_at, node_id) VALUES"
    f" ('{H2}', 'x', 0, 1, 0, '{{\"a\": 1}}', 'k', '2026-07-04T00:00:00.000000+00:00', 'n')",
    "raw-meta-surrogate": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, raw_meta, keyword, observed_at, node_id) VALUES"
    f" ('{H2}', 'x', 0, 1, 0, '[[\"a\", \"\\ud800\"]]', 'k',"
    " '2026-07-04T00:00:00.000000+00:00', 'n')",
    "filename-blob": "INSERT INTO file_observations (ed2k_hash, filename, size_bytes,"
    " source_count, complete_source_count, raw_meta, keyword, observed_at, node_id) VALUES"
    f" ('{H2}', X'ff00', 0, 1, 0, '[]', 'k', '2026-07-04T00:00:00.000000+00:00', 'n')",
    "negative-file-size": f"INSERT INTO files (ed2k_hash, size_bytes) VALUES ('{H4}', -1)",
    "unknown-tier": "INSERT INTO match_decisions (ed2k_hash, target_id, rule_name, tier,"
    f" decided_at, node_id) VALUES ('{H1}', 't', 'r', 'ignore',"
    " '2026-07-04T00:00:00.000000+00:00', 'n')",
    "naive-decided-at": "INSERT INTO match_decisions (ed2k_hash, target_id, rule_name, tier,"
    f" decided_at, node_id) VALUES ('{H1}', 't', 'r', 'catalog', '2026-07-04 00:00:00', 'n')",
    "compacted-day": "INSERT INTO file_observation_ranges (ed2k_hash, bucket, filenames,"
    " node_ids, observation_count, first_observed_at, last_observed_at, source_count_min,"
    " source_count_max, source_count_sum, complete_source_count_min, complete_source_count_max,"
    f" complete_source_count_sum) VALUES ('{H1}', '2026-07-04', '[]', '[]', 1, 'a', 'a', 0, 0, 0,"
    " 0, 0, 0)",
}

LOCAL_EDGES = {
    "node-id-without-created-at": "DELETE FROM node_runtime WHERE key = 'created_at'",
    "no-node-runtime": "DELETE FROM node_runtime",
    "uppercase-download-hash": "INSERT INTO downloads (ed2k_hash, target_id, state, queued_at,"
    " size_bytes, last_seen_at) VALUES ('ABCDEF0123456789ABCDEF0123456789', 't', 'queued',"
    " '2026-07-04T00:00:00.000000+00:00', 1, '2026-07-04T00:00:00.000000+00:00')",
    "naive-queued-at": "INSERT INTO downloads (ed2k_hash, target_id, state, queued_at,"
    f" size_bytes, last_seen_at) VALUES ('{H4}', 't', 'queued', '2026-07-04T00:00:00', 1, NULL)",
    "null-last-seen-at": "INSERT INTO downloads (ed2k_hash, target_id, state, queued_at,"
    f" size_bytes, last_seen_at) VALUES ('{H4}', 't', 'queued',"
    " '2026-07-04T00:00:00.000000+00:00', 1, NULL)",
}


def main() -> None:
    out = Path(sys.argv[1])
    bulk_count = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    expected = make_base(out / "base")
    for case, sql in CATALOG_EDGES.items():
        target = out / f"edge-catalog-{case}"
        shutil.copytree(out / "base", target)
        connection = sqlite3.connect(target / "catalog.db")
        connection.execute(sql)
        connection.commit()
        connection.close()
    for case, sql in LOCAL_EDGES.items():
        target = out / f"edge-local-{case}"
        shutil.copytree(out / "base", target)
        connection = sqlite3.connect(target / "local.db")
        connection.execute(sql)
        connection.commit()
        connection.close()
    if bulk_count:
        shutil.copytree(out / "base", out / "bulk")
        bulk(out / "bulk", bulk_count, str(expected["node_id"]))
    (out / "expected.json").write_text(json.dumps(expected))
    print("created", sorted(p.name for p in out.iterdir()))


main()
