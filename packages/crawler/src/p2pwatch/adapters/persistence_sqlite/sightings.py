"""Every read of a file's observations, as a ``Sighting``."""

import sqlite3
from collections.abc import Iterator
from typing import Any

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import Sighting

# Integer microseconds back to ``utc_iso``'s fixed-width text, in SQL for the read-only reader.
_ISO = (
    "strftime('%Y-%m-%dT%H:%M:%S', {0} / 1000000, 'unixepoch')"
    " || printf('.%06d+00:00', {0} % 1000000)"
)

# Each file's latest observation: its variant with the newest observation, then that variant's
# newest one, each a seek on observations' key. Ties go to the higher variant_id, then the higher
# source_count (stage 1, D4). One row per catalogued file, all NULL for a file never seen.
LATEST_SIGHTING_CTE = f"""latest_sighting AS (
    SELECT
        f.file_id AS file_id,
        f.network AS network,
        f.native_id AS native_id,
        v.filename AS filename,
        {_ISO.format("o.observed_at")} AS last_seen,
        o.source_count AS source_count,
        v.size_bytes AS size_bytes,
        v.duration_seconds AS duration_seconds,
        v.bitrate_kbps AS bitrate_kbps,
        v.keyword AS keyword
    FROM files AS f
    LEFT JOIN observation_variants AS v ON v.variant_id = (
        SELECT v2.variant_id FROM observation_variants AS v2
        WHERE v2.file_id = f.file_id
        ORDER BY (
            SELECT max(o2.observed_at) FROM observations AS o2
            WHERE o2.variant_id = v2.variant_id
        ) DESC, v2.variant_id DESC
        LIMIT 1
    )
    LEFT JOIN observations AS o ON (o.variant_id, o.observed_at, o.source_count) = (
        SELECT o3.variant_id, o3.observed_at, o3.source_count FROM observations AS o3
        WHERE o3.variant_id = v.variant_id
        ORDER BY o3.observed_at DESC, o3.source_count DESC
        LIMIT 1
    )
)"""

# Every query below returns these columns in this order, so ``_sighting`` maps them all.
_COLUMNS = (
    "network, native_id, filename, last_seen, source_count, size_bytes, duration_seconds,"
    " bitrate_kbps, keyword"
)

SELECT_LATEST_SIGHTING = f"""WITH {LATEST_SIGHTING_CTE}
SELECT {_COLUMNS} FROM latest_sighting WHERE file_id = ? AND filename IS NOT NULL
"""

SELECT_LATEST_SIGHTINGS = f"""WITH {LATEST_SIGHTING_CTE}
SELECT {_COLUMNS} FROM latest_sighting WHERE filename IS NOT NULL ORDER BY network, native_id
"""

# The file's timeline in an interval, oldest first; an instant's observations by variant_id, then
# source_count.
_SELECT_SIGHTINGS = f"""
SELECT f.network, f.native_id, v.filename, {_ISO.format("o.observed_at")}, o.source_count,
    v.size_bytes, v.duration_seconds, v.bitrate_kbps, v.keyword
FROM files AS f
JOIN observation_variants AS v ON v.file_id = f.file_id
JOIN observations AS o ON o.variant_id = v.variant_id
WHERE f.file_id = ? AND o.observed_at >= ? AND o.observed_at < ?
ORDER BY o.observed_at, v.variant_id, o.source_count
"""

# Every filename a file was ever seen under (a file-level veto judges them all); a variant is
# only ever written with an observation, so the variants alone hold every filename.
_SELECT_KNOWN_FILENAMES = """
SELECT DISTINCT filename FROM observation_variants WHERE file_id = ? ORDER BY 1
"""

# The filename seen with the most sources, latest seen on a tie, and its size.
_SELECT_BEST_FILENAME_AND_SIZE = """
SELECT v.filename, v.size_bytes
FROM observation_variants AS v
JOIN observations AS o ON o.variant_id = v.variant_id
WHERE v.file_id = ?
ORDER BY o.source_count DESC, o.observed_at DESC, v.filename
LIMIT 1
"""


def _sighting(row: Any) -> Sighting:
    return Sighting(
        file=FileKey(Network(row[0]), row[1]),
        filename=row[2],
        observed_at=row[3],
        source_count=row[4],
        size_bytes=row[5],
        duration_seconds=row[6],
        bitrate_kbps=row[7],
        keyword=row[8],
    )


def latest_sighting(connection: sqlite3.Connection, file: FileKey) -> Sighting | None:
    """The latest observation; ``None`` for a file never seen."""
    row = connection.execute(SELECT_LATEST_SIGHTING, (file.file_id,)).fetchone()
    return None if row is None else _sighting(row)


def iter_latest_sightings(connection: sqlite3.Connection) -> Iterator[Sighting]:
    """Each seen file's latest sighting, sorted by network and native id, streamed."""
    return map(_sighting, connection.execute(SELECT_LATEST_SIGHTINGS))


def known_filenames(connection: sqlite3.Connection, file: FileKey) -> tuple[str, ...]:
    """Every distinct filename of the file, sorted."""
    rows = connection.execute(_SELECT_KNOWN_FILENAMES, (file.file_id,)).fetchall()
    return tuple(row[0] for row in rows)


def best_filename_and_size(connection: sqlite3.Connection, file: FileKey) -> tuple[str, int] | None:
    """The clean filename (most sources, then latest) and its size; ``None`` if never seen."""
    row = connection.execute(_SELECT_BEST_FILENAME_AND_SIZE, (file.file_id,)).fetchone()
    return None if row is None else (row[0], row[1])


def sightings(
    connection: sqlite3.Connection, file: FileKey, since: int, until: int
) -> tuple[Sighting, ...]:
    """The file's timeline from ``since`` included to ``until`` excluded, in microseconds, oldest
    first."""
    rows = connection.execute(_SELECT_SIGHTINGS, (file.file_id, since, until)).fetchall()
    return tuple(map(_sighting, rows))
