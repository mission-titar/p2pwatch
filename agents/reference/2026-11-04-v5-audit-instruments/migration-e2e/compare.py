"""Compares a 4.x data/ (catalog v5, local v5) with its 5.0 migration, read-only both sides.

compare.py ORIGINAL_DATA MIGRATED_DATA
Prints one line per check, ``OK`` or ``DIFF``, and a summary. Expectations come from
docs/migration-4x.md, re-derived here rather than from the migration's SQL functions.
"""

import json
import sqlite3
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from p2pwatch.domain import file_key

NAMESPACE = file_key._NAMESPACE  # noqa: SLF001  the uuid5 namespace is the spec, not the logic
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
failures: list[str] = []


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"{'OK  ' if ok else 'DIFF'} {name} {detail}")
    if not ok:
        failures.append(name)


def micros(stamp: str) -> int:
    instant = datetime.fromisoformat(stamp)
    assert instant.tzinfo is not None, stamp
    delta = instant - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def fid(native: str) -> bytes:
    return uuid.uuid5(NAMESPACE, f"ed2k:{native}").bytes


def expected_raw(pairs_text: str, codec, file_type, complete) -> dict:
    unmapped: dict = {}
    media: dict = {}
    for name, value in json.loads(pairs_text):
        if name.startswith("media."):
            media[name.removeprefix("media.")] = value
        else:
            unmapped[name] = value
    if media:
        unmapped["media"] = media
    return {"codec": codec, "file_type": file_type, "complete_source_count": complete, "unmapped": unmapped}


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def compare_catalog(original: sqlite3.Connection, migrated: sqlite3.Connection) -> None:
    check("catalog user_version", migrated.execute("PRAGMA user_version").fetchone()[0] == 15,
          migrated.execute("PRAGMA user_version").fetchone()[0])
    integrity = migrated.execute("PRAGMA integrity_check").fetchall()
    check("catalog integrity_check", [r[0] for r in integrity] == ["ok"], integrity[:3])
    check("catalog foreign_key_check", migrated.execute("PRAGMA foreign_key_check").fetchall() == [])
    tables = {r["name"]: r["strict"] for r in migrated.execute("PRAGMA table_list") if r["schema"] == "main" and not r["name"].startswith("sqlite_")}
    check("catalog tables", sorted(tables) == sorted(["files", "match_decisions", "observation_variants", "observations", "sources", "source_variants", "source_observations"]), sorted(tables))
    check("catalog every table STRICT", all(tables.values()), tables)
    leftovers = [r[0] for r in migrated.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_old' OR name LIKE 'migration_%'")]
    check("catalog no leftover table", leftovers == [], leftovers)

    # files
    orig_files = {r["ed2k_hash"]: r["size_bytes"] for r in original.execute("SELECT ed2k_hash, size_bytes FROM files")}
    mig_files = {r["native_id"]: (r["file_id"], r["network"], r["size_bytes"]) for r in migrated.execute("SELECT * FROM files")}
    check("files count", len(orig_files) == len(mig_files), (len(orig_files), len(mig_files)))
    bad = [h for h, size in orig_files.items() if mig_files.get(h) != (fid(h), "ed2k", size)]
    check("files field by field (file_id, network, size)", not bad, bad[:3])
    # sizes per observation the 5.0 drops: do they ever differ from the file's?
    differing = original.execute(
        "SELECT COUNT(*) FROM file_observations o JOIN files f USING (ed2k_hash) WHERE o.size_bytes <> f.size_bytes"
    ).fetchone()[0]
    check("observation sizes all equal to files.size_bytes (none lost)", differing == 0, differing)

    # observations: every original row maps onto an observation, and every observation onto a row
    total_rows = duplicates = 0
    mismatched_files = []
    raw_type_errors = 0
    for (hash_,) in original.execute("SELECT ed2k_hash FROM files ORDER BY ed2k_hash"):
        expected: Counter = Counter()
        for r in original.execute(
            "SELECT filename, media_length_sec, bitrate_kbps, raw_meta, codec, file_type, complete_source_count,"
            " keyword, node_id, observed_at, source_count FROM file_observations WHERE ed2k_hash = ?", (hash_,)
        ):
            key = (r["filename"], r["media_length_sec"], r["bitrate_kbps"],
                   canonical(expected_raw(r["raw_meta"], r["codec"], r["file_type"], r["complete_source_count"])),
                   r["keyword"], r["node_id"], micros(r["observed_at"]), r["source_count"])
            expected[key] += 1
            total_rows += 1
        duplicates += sum(count - 1 for count in expected.values())
        found = set()
        for r in migrated.execute(
            "SELECT v.filename, v.duration_seconds, v.bitrate_kbps, v.raw_metadata, v.keyword, v.node_id,"
            " o.observed_at_micros, o.source_count FROM observation_variants v JOIN observations o USING (variant_id)"
            " WHERE v.file_id = ?", (fid(hash_),)
        ):
            raw = json.loads(r["raw_metadata"])
            if not isinstance(raw, dict) or "unmapped" not in raw:
                raw_type_errors += 1
            found.add((r["filename"], r["duration_seconds"], r["bitrate_kbps"], canonical(raw),
                       r["keyword"], r["node_id"], r["observed_at_micros"], r["source_count"]))
        if found != set(expected):
            mismatched_files.append((hash_, len(expected), len(found), len(set(expected) - found), len(found - set(expected))))
    observations = migrated.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    print(f"     original file_observations rows: {total_rows}, exact duplicates folded: {duplicates}, observations: {observations}")
    check("observations == original rows minus exact duplicates", observations == total_rows - duplicates,
          (observations, total_rows, duplicates))
    check("observations bijection per file (all columns, raw_metadata as JSON object)", not mismatched_files, mismatched_files[:5])
    check("raw_metadata always an object with 'unmapped'", raw_type_errors == 0, raw_type_errors)
    variants = migrated.execute("SELECT COUNT(*) FROM observation_variants").fetchone()[0]
    orphans = migrated.execute("SELECT COUNT(*) FROM observation_variants v WHERE NOT EXISTS (SELECT 1 FROM observations o WHERE o.variant_id = v.variant_id)").fetchone()[0]
    check("no variant without observation", orphans == 0, (variants, orphans))
    # the doc's example: media.title becomes unmapped.media.title
    media = original.execute("SELECT COUNT(*) FROM file_observations WHERE raw_meta LIKE '%\"media.%'").fetchone()[0]
    migrated_media = migrated.execute("SELECT COUNT(*) FROM observation_variants WHERE json_extract(raw_metadata, '$.unmapped.media') IS NOT NULL").fetchone()[0]
    print(f"     original rows with a media.* pair: {media}; migrated variants with unmapped.media: {migrated_media}")
    repeated = 0
    for (text,) in original.execute("SELECT DISTINCT raw_meta FROM file_observations"):
        names = [name for name, _ in json.loads(text)]
        repeated += len(names) != len(set(names))
    check("no v4 raw_meta repeats a name (the fold keeps the last value)", repeated == 0, repeated)

    # match_decisions, by id
    orig_decisions = {r["id"]: (fid(r["ed2k_hash"]), r["target_id"], r["rule_name"], r["tier"], micros(r["decided_at"]), r["node_id"])
                      for r in original.execute("SELECT * FROM match_decisions")}
    mig_decisions = {r["id"]: (r["file_id"], r["target_id"], r["rule_name"], r["tier"], r["decided_at_micros"], r["node_id"])
                     for r in migrated.execute("SELECT * FROM match_decisions")}
    missing = [i for i, row in orig_decisions.items() if mig_decisions.get(i) != row]
    check("match_decisions: every original row, field by field", not missing, missing[:3])
    extra = sorted(set(mig_decisions) - set(orig_decisions))
    print(f"     match_decisions original {len(orig_decisions)}, migrated {len(mig_decisions)}, written after (ids > {max(orig_decisions)}): {len(extra)}")
    check("sources/source_* empty as in the original", all(
        migrated.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in ("sources", "source_variants", "source_observations")
    ) and original.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0)


def compare_local(original: sqlite3.Connection, migrated: sqlite3.Connection) -> None:
    check("local user_version", migrated.execute("PRAGMA user_version").fetchone()[0] == 15)
    check("local integrity_check", migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
    tables = {r["name"]: r["strict"] for r in migrated.execute("PRAGMA table_list") if r["schema"] == "main" and not r["name"].startswith("sqlite_")}
    check("local tables", sorted(tables) == ["backoff_states", "downloads", "node_identity", "reevaluation_state"], tables)
    runtime = {r["key"]: r["value"] for r in original.execute("SELECT * FROM node_runtime")}
    identity = migrated.execute("SELECT * FROM node_identity").fetchall()
    check("node_identity = node_runtime", [tuple(r) for r in identity] == [(1, runtime["node_id"], micros(runtime["created_at"]))])
    orig_state = original.execute("SELECT policy_sha256 FROM backfill_state").fetchone()[0]
    mig_state = migrated.execute("SELECT policy_fingerprint FROM reevaluation_state").fetchone()[0]
    print(f"     reevaluation fingerprint unchanged since 4.x: {orig_state == mig_state}")
    print(f"     backoff_states rows: {migrated.execute('SELECT COUNT(*) FROM backoff_states').fetchone()[0]}")

    def opt(value):
        return None if value is None else micros(value)

    orig = {fid(r["ed2k_hash"]): r for r in original.execute("SELECT * FROM downloads")}
    mig = {r["file_id"]: r for r in migrated.execute("SELECT * FROM downloads")}
    check("downloads count", len(orig) == len(mig), (len(orig), len(mig)))
    stable, moved = [], []
    for key, o in orig.items():
        m = mig.get(key)
        if m is None:
            stable.append(("missing", o["ed2k_hash"]))
            continue
        if (m["native_id"], m["network"], m["target_id"], m["queued_at_micros"]) != (o["ed2k_hash"], "ed2k", o["target_id"], micros(o["queued_at"])):
            stable.append(o["ed2k_hash"])
        if (m["state"], m["completed_at_micros"], m["latest_seen_at_micros"]) != (o["state"], opt(o["completed_at"]), opt(o["last_seen_at"])):
            moved.append((o["ed2k_hash"][:8], o["state"], m["state"], m["latest_seen_at_micros"] and datetime.fromtimestamp(m["latest_seen_at_micros"] / 1e6, UTC).isoformat()))
    check("downloads: identity, target, queued_at field by field", not stable, stable[:3])
    check("downloads: state, completed_at, latest_seen_at unchanged (the loop may have run since)", not moved, moved[:5])


def main() -> None:
    original, migrated = Path(sys.argv[1]), Path(sys.argv[2])
    parts = sys.argv[3:] or ["catalog", "local"]
    if "local" in parts:
        compare_local(connect(original / "local.db"), connect(migrated / "local.db"))
    if "catalog" in parts:
        compare_catalog(connect(original / "catalog.db"), connect(migrated / "catalog.db"))
    print("SUMMARY", "all OK" if not failures else f"{len(failures)} DIFF: {failures}")


main()
