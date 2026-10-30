"""Every read of a file's observations, as a ``FileObservation``."""

import json
import sqlite3
from collections.abc import Iterator

from p2pwatch.adapters.driven.persistence_sqlite.micros import micros_to_instant
from p2pwatch.adapters.driven.persistence_sqlite.named_row import NamedRow
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile

# Each file's latest observation: its variant with the newest observation, then that variant's
# newest one, each a seek on observations' key. Ties go to the higher variant_id, then the higher
# source_count (stage 1, D4). One row per catalogued file, all NULL for a file never seen.
LATEST_OBSERVATION_CTE = """latest_observation AS (
    SELECT
        f.file_id AS file_id,
        f.network AS network,
        f.native_id AS native_id,
        v.filename AS filename,
        v.size_bytes AS size_bytes,
        o.source_count AS source_count,
        v.keyword AS keyword,
        v.duration_seconds AS duration_seconds,
        v.bitrate_kbps AS bitrate_kbps,
        v.raw_metadata AS raw_metadata,
        o.observed_at_micros AS observed_at_micros,
        v.node_id AS node_id
    FROM files AS f
    LEFT JOIN observation_variants AS v ON v.variant_id = (
        SELECT v2.variant_id FROM observation_variants AS v2
        WHERE v2.file_id = f.file_id
        ORDER BY (
            SELECT max(o2.observed_at_micros) FROM observations AS o2
            WHERE o2.variant_id = v2.variant_id
        ) DESC, v2.variant_id DESC
        LIMIT 1
    )
    LEFT JOIN observations AS o ON (o.variant_id, o.observed_at_micros, o.source_count) = (
        SELECT o3.variant_id, o3.observed_at_micros, o3.source_count FROM observations AS o3
        WHERE o3.variant_id = v.variant_id
        ORDER BY o3.observed_at_micros DESC, o3.source_count DESC
        LIMIT 1
    )
)"""

# Every query below returns these columns, which ``observation_from_row`` reads by name.
_COLUMNS = (
    "network, native_id, filename, size_bytes, source_count, keyword, duration_seconds,"
    " bitrate_kbps, raw_metadata, observed_at_micros, node_id"
)

SELECT_LATEST_OBSERVATION = f"""WITH {LATEST_OBSERVATION_CTE}
SELECT {_COLUMNS} FROM latest_observation WHERE file_id = ? AND filename IS NOT NULL
"""

SELECT_LATEST_OBSERVATIONS = f"""WITH {LATEST_OBSERVATION_CTE}
SELECT {_COLUMNS} FROM latest_observation WHERE filename IS NOT NULL ORDER BY network, native_id
"""

_FROM_OBSERVATIONS = """
SELECT f.network, f.native_id, v.filename, v.size_bytes, o.source_count, v.keyword,
    v.duration_seconds, v.bitrate_kbps, v.raw_metadata, o.observed_at_micros, v.node_id
FROM files AS f
JOIN observation_variants AS v ON v.file_id = f.file_id
JOIN observations AS o ON o.variant_id = v.variant_id
"""

# The file's timeline in an interval, oldest first; an instant's observations by variant_id, then
# source_count.
_SELECT_OBSERVATIONS_BETWEEN = (
    _FROM_OBSERVATIONS
    + """WHERE f.file_id = ? AND o.observed_at_micros >= ? AND o.observed_at_micros < ?
ORDER BY o.observed_at_micros, v.variant_id, o.source_count
"""
)

# Every filename a file was ever seen under (a file-level veto judges them all); a variant is
# only ever written with an observation, so the variants alone hold every filename.
_SELECT_KNOWN_FILENAMES = """
SELECT DISTINCT filename FROM observation_variants WHERE file_id = ? ORDER BY 1
"""

# The observation with the most sources, latest seen on a tie: the file's clean filename.
_SELECT_BEST_OBSERVATION = (
    _FROM_OBSERVATIONS
    + """WHERE f.file_id = ?
ORDER BY o.source_count DESC, o.observed_at_micros DESC, v.filename
LIMIT 1
"""
)


def observation_from_row(row: NamedRow) -> FileObservation:
    reported_file = ReportedFile(
        file=FileKey(network=Network(row["network"]), native_id=row["native_id"]),
        filename=row["filename"],
        size_bytes=row["size_bytes"],
        source_count=row["source_count"],
        keyword=Keyword(row["keyword"]),
        duration_seconds=row["duration_seconds"],
        bitrate_kbps=row["bitrate_kbps"],
        raw_metadata=tuple((name, rendered) for name, rendered in json.loads(row["raw_metadata"])),
    )
    return FileObservation(
        reported_file=reported_file,
        observed_at=micros_to_instant(row["observed_at_micros"]),
        node_id=NodeId(row["node_id"]),
    )


def latest_observation(connection: sqlite3.Connection, file: FileKey) -> FileObservation | None:
    """The latest observation; ``None`` for a file never seen."""
    row = connection.execute(SELECT_LATEST_OBSERVATION, (file.file_id,)).fetchone()
    return None if row is None else observation_from_row(row)


def iter_latest_observations(connection: sqlite3.Connection) -> Iterator[FileObservation]:
    """Each seen file's latest observation, sorted by network and native id, streamed."""
    return map(observation_from_row, connection.execute(SELECT_LATEST_OBSERVATIONS))


def known_filenames(connection: sqlite3.Connection, file: FileKey) -> tuple[str, ...]:
    """Every distinct filename of the file, sorted."""
    rows = connection.execute(_SELECT_KNOWN_FILENAMES, (file.file_id,)).fetchall()
    return tuple(row["filename"] for row in rows)


def best_observation(connection: sqlite3.Connection, file: FileKey) -> FileObservation | None:
    """The observation of the clean filename (most sources, then latest); ``None`` if never seen."""
    row = connection.execute(_SELECT_BEST_OBSERVATION, (file.file_id,)).fetchone()
    return None if row is None else observation_from_row(row)


def observations_between(
    connection: sqlite3.Connection, file: FileKey, since: int, until: int
) -> tuple[FileObservation, ...]:
    """The file's timeline from ``since`` included to ``until`` excluded, in microseconds, oldest
    first."""
    rows = connection.execute(_SELECT_OBSERVATIONS_BETWEEN, (file.file_id, since, until)).fetchall()
    return tuple(map(observation_from_row, rows))
