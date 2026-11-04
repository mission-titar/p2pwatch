"""Opens v4.1.0-made databases with main's opener, then checks every value field by field.

Usage: uv run python main_check.py <dbs_dir> (from packages/crawler of main).
Expected values are computed here from the v4 rows, independently of main's SQL functions.
"""

import json
import shutil
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from shutil import disk_usage

from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_id_store import SqliteNodeIdStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_policy_fingerprint_store import (
    SqlitePolicyFingerprintStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from p2pwatch.domain.file_key import FileKey, Network

NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://mission-titar.github.io/p2pwatch/file")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
failures: list[str] = []


def check(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        failures.append(f"{label}: got {actual!r}, expected {expected!r}")


def file_id(native_id: str) -> bytes:
    return uuid.uuid5(NAMESPACE, f"ed2k:{native_id}").bytes


def micros(stamp: str) -> int:
    delta = datetime.fromisoformat(stamp) - EPOCH
    return 1 + delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds


def fold(raw: str, codec: str | None, file_type: str | None, complete: int) -> str:
    unmapped: dict[str, object] = {}
    media: dict[str, str] = {}
    for name, value in json.loads(raw):
        if name.startswith("media."):
            media[name[len("media."):]] = value.upper()
        else:
            unmapped[name] = value
    if media:
        unmapped["media"] = media
    return json.dumps(
        {"codec": codec, "complete_source_count": complete, "file_type": file_type,
         "unmapped": unmapped},
        ensure_ascii=False, sort_keys=True,
    )


def opener() -> SqliteDatabaseOpener:
    return SqliteDatabaseOpener(
        SqlitePreMigrationCopier(SystemWallClock(), free_bytes=lambda d: disk_usage(d).free)
    )


def rows(path: Path, sql: str) -> list[sqlite3.Row]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    result = connection.execute(sql).fetchall()
    connection.close()
    return result


def version(path: Path) -> int:
    return int(rows(path, "PRAGMA user_version")[0][0])


def check_base(directory: Path, v4: Path) -> None:
    """``v4`` is an untouched copy of ``directory`` before main opened it."""
    old_files = rows(v4 / "catalog.db", "SELECT * FROM files")
    old_obs = rows(v4 / "catalog.db", "SELECT * FROM file_observations ORDER BY id")
    old_dec = rows(v4 / "catalog.db", "SELECT * FROM match_decisions ORDER BY id")
    old_runtime = {r["key"]: r["value"] for r in rows(v4 / "local.db", "SELECT * FROM node_runtime")}
    old_downloads = rows(v4 / "local.db", "SELECT * FROM downloads ORDER BY ed2k_hash")
    old_backfill = rows(v4 / "local.db", "SELECT * FROM backfill_state")

    db_opener = opener()
    catalog = db_opener.open_catalog(directory / "catalog.db")
    local = db_opener.open_local(directory / "local.db")

    new_files = {r["native_id"]: r for r in catalog.execute("SELECT * FROM files")}
    check("files count", len(new_files), len(old_files))
    for old in old_files:
        new = new_files[old["ed2k_hash"]]
        check(f"files {old['ed2k_hash']} file_id", new["file_id"], file_id(old["ed2k_hash"]))
        check(f"files {old['ed2k_hash']} network", new["network"], "ed2k")
        check(f"files {old['ed2k_hash']} size_bytes", new["size_bytes"], old["size_bytes"])

    variants = {
        (r["file_id"], r["filename"], r["duration_seconds"], r["bitrate_kbps"], r["raw_metadata"],
         r["keyword"], r["node_id"]): r["variant_id"]
        for r in catalog.execute("SELECT * FROM observation_variants")
    }
    observations = {
        (r["variant_id"], r["observed_at_micros"], r["source_count"])
        for r in catalog.execute("SELECT * FROM observations")
    }
    expected_observations = set()
    for old in old_obs:
        key = (file_id(old["ed2k_hash"]), old["filename"], old["media_length_sec"],
               old["bitrate_kbps"],
               fold(old["raw_meta"], old["codec"], old["file_type"], old["complete_source_count"]),
               old["keyword"], old["node_id"])
        if key not in variants:
            failures.append(f"observation {old['id']}: no variant {key!r}")
            continue
        expected_observations.add((variants[key], micros(old["observed_at"]), old["source_count"]))
    check("observations", observations, expected_observations)
    check("variant count", len(variants), len({k for k in variants}))
    print(f"   base: {len(old_obs)} v4 observations -> {len(variants)} variants, "
          f"{len(observations)} observations")
    print("   raw_metadata of the repeated-name row:",
          [k[4] for k in variants if k[1] == "dup names"])

    new_dec = list(catalog.execute("SELECT * FROM match_decisions ORDER BY id"))
    check("decision count", len(new_dec), len(old_dec))
    for old, new in zip(old_dec, new_dec, strict=False):
        for column in ("id", "target_id", "rule_name", "tier", "node_id"):
            check(f"decision {old['id']} {column}", new[column], old[column])
        check(f"decision {old['id']} file_id", new["file_id"], file_id(old["ed2k_hash"]))
        check(f"decision {old['id']} decided_at_micros", new["decided_at_micros"],
              micros(old["decided_at"]))

    node = local.execute("SELECT * FROM node_identity").fetchall()
    check("node_identity rows", len(node), 1)
    check("node_identity node_id", node[0]["node_id"], old_runtime["node_id"])
    check("node_identity created_at_micros", node[0]["created_at_micros"],
          micros(old_runtime["created_at"]))
    check("reevaluation_state", [tuple(r.values()) for r in local.execute("SELECT * FROM reevaluation_state")],
          [(r["id"], r["policy_sha256"]) for r in old_backfill])
    new_downloads = {r["native_id"]: r for r in local.execute("SELECT * FROM downloads")}
    check("download count", len(new_downloads), len(old_downloads))
    for old in old_downloads:
        new = new_downloads[old["ed2k_hash"]]
        h = old["ed2k_hash"]
        check(f"download {h} file_id", new["file_id"], file_id(h))
        for column in ("target_id", "state"):
            check(f"download {h} {column}", new[column], old[column])
        check(f"download {h} queued", new["queued_at_micros"], micros(old["queued_at"]))
        check(f"download {h} completed", new["completed_at_micros"],
              None if old["completed_at"] is None else micros(old["completed_at"]))
        check(f"download {h} latest_seen", new["latest_seen_at_micros"],
              None if old["last_seen_at"] is None else micros(old["last_seen_at"]))
        for column in ("bytes_done", "latest_progress_at_micros", "waiting_reason",
                       "failure_reason"):
            check(f"download {h} {column}", new[column], None)
    check("backoff_states", local.execute("SELECT COUNT(*) AS n FROM backoff_states").fetchone()["n"], 0)
    tables = {r["name"] for r in local.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check("local tables", tables, {"node_identity", "reevaluation_state", "downloads", "backoff_states"})
    strict = {r["name"]: r["strict"] for r in catalog.execute("PRAGMA table_list") if r["schema"] == "main" and not r["name"].startswith("sqlite_")}
    check("catalog strict", set(strict.values()), {1})
    strict_local = {r["name"]: r["strict"] for r in local.execute("PRAGMA table_list") if r["schema"] == "main" and not r["name"].startswith("sqlite_")}
    check("local strict", set(strict_local.values()), {1})
    for name, connection in (("catalog", catalog), ("local", local)):
        check(f"{name} quick_check", connection.execute("PRAGMA quick_check").fetchone()[0] if False else list(connection.execute("PRAGMA quick_check").fetchone().values()), ["ok"])
        check(f"{name} foreign_key_check", connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    # Through main's stores, as the crawler reads them.
    check("node id store", SqliteNodeIdStore(local).read_node_id(), old_runtime["node_id"])
    check("fingerprint store", SqlitePolicyFingerprintStore(local).read_policy_fingerprint(),
          old_backfill[0]["policy_sha256"])
    tracked = SqliteTrackedDownloadStore(local).read_tracked_states()
    check("tracked states", {k.native_id: v.value for k, v in tracked.items()},
          {r["ed2k_hash"]: r["state"] for r in old_downloads})
    decisions = SqliteDecisionStore(catalog)
    h1 = FileKey(network=Network.ED2K, native_id="0123456789abcdef0123456789abcdef")
    latest = decisions.read_latest_decisions(h1)
    print("   latest decisions of H1:", {k: type(v).__name__ + ":" + str(getattr(v, "tier", "")) for k, v in latest.items()})
    print("   download candidates:", decisions.read_download_candidates())
    store = SqliteObservationStore(catalog)
    print("   latest observation of H1:", store.read_latest_observation(h1))
    catalog.close()
    local.close()


def open_case(directory: Path) -> str:
    db_opener = opener()
    outcome = []
    for name, open_db in (("catalog", db_opener.open_catalog), ("local", db_opener.open_local)):
        try:
            open_db(directory / f"{name}.db").close()
            outcome.append(f"{name}: migrated")
        except MigrationError as error:
            outcome.append(f"{name}: MigrationError {error}")
            break
        except Exception as error:  # noqa: BLE001
            outcome.append(f"{name}: {type(error).__name__} {error}")
            break
    versions = {p.name: version(p) for p in sorted(directory.glob("*.db"))}
    copies = sorted(p.name.split(".pre-")[0] + ".pre-" + p.name.split(".pre-")[1][:4] for p in directory.glob("*.pre-*"))
    return f"{'; '.join(outcome)} | versions {versions} | copies {copies}"


def main() -> None:
    dbs = Path(sys.argv[1])
    pristine = dbs / "pristine-base"
    if not pristine.exists():
        shutil.copytree(dbs / "base", pristine)
    print("== base, field by field")
    check_base(dbs / "base", pristine)
    print("   copies:", sorted(p.name for p in (dbs / "base").glob("*.pre-*")))
    for copy in (dbs / "base").glob("*.pre-*"):
        db_name = copy.name.split(".pre-")[0]
        check(f"{copy.name} user_version", version(copy), 5)
        check(f"{copy.name} rows equal the v4 database",
              rows(copy, "SELECT * FROM sqlite_master ORDER BY name") and
              [tuple(r) for r in rows(copy, "SELECT name, sql FROM sqlite_master ORDER BY name")],
              [tuple(r) for r in rows(pristine / db_name, "SELECT name, sql FROM sqlite_master ORDER BY name")])
    print("== reopen base (idempotent):", open_case(dbs / "base"))
    for case in sorted(dbs.glob("edge-*")):
        print(f"== {case.name}: {open_case(case)}")
    print("FAILURES:" if failures else "ALL FIELD CHECKS PASSED")
    for failure in failures:
        print("  ", failure)


main()
