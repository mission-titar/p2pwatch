"""Read-only SQL scan of the real node's databases for rows the v5 migrations would reject or alter."""

import sqlite3
import sys
import time

CATALOG = "file:/home/geoffrey/Projets/mulewatch/data/catalog.db?mode=ro"
LOCAL = "file:/home/geoffrey/Projets/mulewatch/data/local.db?mode=ro"

STAMP_GLOB = (
    "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
    ".[0-9][0-9][0-9][0-9][0-9][0-9]+00:00"
)
HEX_GLOB = "*[^0-9a-f]*"

CATALOG_QUERIES = {
    "files: total": "SELECT COUNT(*) FROM files",
    "files: size_bytes not integer": "SELECT COUNT(*) FROM files WHERE typeof(size_bytes) <> 'integer'",
    "files: size_bytes < 0": "SELECT COUNT(*) FROM files WHERE size_bytes < 0",
    "files: aich_hash not null (dropped by 0008)": "SELECT COUNT(*) FROM files WHERE aich_hash IS NOT NULL",
    "files: ed2k_hash not canonical": (
        f"SELECT COUNT(*) FROM files WHERE LENGTH(ed2k_hash) <> 32 OR ed2k_hash GLOB '{HEX_GLOB}'"
        " OR typeof(ed2k_hash) <> 'text'"
    ),
    "file_observations: per-column anomalies (one scan)": f"""
        SELECT
            COUNT(*) AS total,
            SUM(typeof(source_count) <> 'integer') AS source_count_not_int,
            SUM(source_count < 0) AS source_count_negative,
            SUM(typeof(complete_source_count) <> 'integer') AS complete_not_int,
            SUM(complete_source_count < 0) AS complete_negative,
            SUM(media_length_sec IS NOT NULL AND typeof(media_length_sec) <> 'integer')
                AS length_not_int,
            SUM(media_length_sec < 0) AS length_negative,
            SUM(bitrate_kbps IS NOT NULL AND typeof(bitrate_kbps) <> 'integer') AS bitrate_not_int,
            SUM(bitrate_kbps < 0) AS bitrate_negative,
            SUM(typeof(filename) <> 'text') AS filename_not_text,
            SUM(typeof(keyword) <> 'text') AS keyword_not_text,
            SUM(typeof(node_id) <> 'text') AS node_id_not_text,
            SUM(typeof(raw_meta) <> 'text') AS raw_meta_not_text,
            SUM(codec IS NOT NULL AND typeof(codec) <> 'text') AS codec_not_text,
            SUM(file_type IS NOT NULL AND typeof(file_type) <> 'text') AS file_type_not_text,
            SUM(typeof(observed_at) <> 'text' OR observed_at NOT GLOB '{STAMP_GLOB}')
                AS observed_at_not_fixed_utc,
            SUM(json_valid(raw_meta) = 0) AS raw_meta_invalid_json,
            SUM(json_valid(raw_meta) = 1 AND json_type(raw_meta) <> 'array') AS raw_meta_not_array,
            SUM(typeof(size_bytes) <> 'integer') AS size_not_int,
            MIN(observed_at) AS min_observed_at,
            MAX(observed_at) AS max_observed_at,
            MIN(source_count) AS min_source_count,
            MAX(source_count) AS max_source_count,
            MAX(media_length_sec) AS max_length,
            MAX(bitrate_kbps) AS max_bitrate
        FROM file_observations
    """,
    "file_observations: size_bytes differs from files.size_bytes (dropped by 0007)": """
        SELECT COUNT(*), COUNT(DISTINCT o.ed2k_hash)
        FROM file_observations AS o JOIN files AS f USING (ed2k_hash)
        WHERE o.size_bytes IS NOT f.size_bytes
    """,
    "file_observations: orphan ed2k_hash (no files row)": """
        SELECT COUNT(*) FROM file_observations AS o
        WHERE NOT EXISTS (SELECT 1 FROM files AS f WHERE f.ed2k_hash = o.ed2k_hash)
    """,
    "file_observations: (ed2k_hash, observed_at) groups with >1 row (dedup upper bound)": """
        SELECT COUNT(*), COALESCE(SUM(n - 1), 0) FROM (
            SELECT COUNT(*) AS n FROM file_observations INDEXED BY idx_file_observations_hash_observed
            GROUP BY ed2k_hash, observed_at HAVING n > 1
        )
    """,
    "match_decisions: tiers": "SELECT tier, typeof(tier), COUNT(*) FROM match_decisions GROUP BY 1, 2",
    "match_decisions: anomalies": f"""
        SELECT
            COUNT(*),
            SUM(typeof(decided_at) <> 'text' OR decided_at NOT GLOB '{STAMP_GLOB}'),
            SUM(typeof(target_id) <> 'text'),
            SUM(typeof(rule_name) <> 'text'),
            SUM(typeof(node_id) <> 'text'),
            MIN(decided_at), MAX(decided_at),
            SUM(NOT EXISTS (SELECT 1 FROM files AS f WHERE f.ed2k_hash = d.ed2k_hash))
        FROM match_decisions AS d
    """,
    "match_decisions: duplicate (hash, target, decided_at) ties": """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM match_decisions GROUP BY ed2k_hash, target_id, decided_at HAVING COUNT(*) > 1
        )
    """,
    "sources / source_observations / file_observation_ranges": (
        "SELECT (SELECT COUNT(*) FROM sources), (SELECT COUNT(*) FROM source_observations),"
        " (SELECT COUNT(*) FROM file_observation_ranges)"
    ),
    "node_ids in file_observations": "SELECT node_id, COUNT(*) FROM file_observations GROUP BY 1",
    "pragma integrity (quick_check)": "PRAGMA quick_check",
    "pragma foreign_key_check": "PRAGMA foreign_key_check",
}

LOCAL_QUERIES = {
    "node_runtime": "SELECT key, typeof(value), value GLOB '" + STAMP_GLOB + "' FROM node_runtime",
    "scheduler_state keys": "SELECT key, typeof(value) FROM scheduler_state",
    "backfill_state": "SELECT id, typeof(policy_sha256), LENGTH(policy_sha256) FROM backfill_state",
    "downloads: states": "SELECT state, COUNT(*) FROM downloads GROUP BY 1",
    "downloads: anomalies": f"""
        SELECT
            COUNT(*),
            SUM(LENGTH(ed2k_hash) <> 32 OR ed2k_hash GLOB '{HEX_GLOB}'),
            SUM(queued_at NOT GLOB '{STAMP_GLOB}'),
            SUM(completed_at IS NOT NULL AND completed_at NOT GLOB '{STAMP_GLOB}'),
            SUM(last_seen_at IS NULL),
            SUM(last_seen_at IS NOT NULL AND last_seen_at NOT GLOB '{STAMP_GLOB}'),
            SUM(typeof(target_id) <> 'text'),
            SUM(typeof(size_bytes) <> 'integer'),
            SUM(size_bytes = 0)
        FROM downloads
    """,
    "pragma integrity (quick_check)": "PRAGMA quick_check",
}


def run(uri: str, queries: dict[str, str]) -> None:
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    for label, sql in queries.items():
        started = time.monotonic()
        rows = connection.execute(sql).fetchall()
        print(f"-- {label} ({time.monotonic() - started:.1f}s)")
        for row in rows[:50]:
            print("  ", row)
        sys.stdout.flush()
    connection.close()


print("== local.db")
run(LOCAL, LOCAL_QUERIES)
print("== catalog.db")
run(CATALOG, CATALOG_QUERIES)
