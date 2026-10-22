"""Read-only reads of the catalog (webui spec W-D6 / §6).

``SqliteCoverageReader.read_target_coverage()``: per ``target_id``, the tier of each file's
LATEST match decision **per target** (ROW_NUMBER window PARTITION BY ``(file_id, target_id)``),
so a whole-episode file contributes to every target it matches. The legacy ``target_id=''``
sentinel and per-target ``retracted`` rows are excluded.

All SQL lives in module constants, parameterized (no value interpolation).
"""

from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.application.ports.driven.coverage_reader import CoverageReader

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Latest decision per (file_id, target_id) via ROW_NUMBER window: a whole-episode file holds
# one CURRENT decision per target it satisfies, so it must contribute to each of them, not
# just the single most-recent row across all its targets. The legacy target_id='' sentinel
# (pre-per-target retraction model) is excluded, and a per-target "retracted" latest decision
# (retracted == unmatched for that target) is dropped too.
_SQL_COVERAGE = """\
SELECT
    ld.file_id,
    ld.target_id,
    ld.tier
FROM (
    SELECT
        md.file_id,
        md.target_id,
        md.tier,
        ROW_NUMBER() OVER (
            PARTITION BY md.file_id, md.target_id
            ORDER BY md.decided_at DESC, md.id DESC
        ) AS rn
    FROM match_decisions AS md
) AS ld
WHERE ld.rn = 1
AND ld.target_id != ''
AND ld.tier != 'retracted'
ORDER BY ld.target_id, ld.file_id
"""


class SqliteCoverageReader(CoverageReader):
    """Reads through the calling thread's read-only connection."""

    def __init__(self, reader_provider: ThreadReadConnections) -> None:
        self._reader_provider = reader_provider

    def read_target_coverage(self) -> dict[str, tuple[str, ...]]:
        tiers_by_target: dict[str, list[str]] = {}
        for row in self._reader_provider.connection().execute(_SQL_COVERAGE):
            tiers_by_target.setdefault(row["target_id"], []).append(row["tier"])
        return {target_id: tuple(tiers) for target_id, tiers in tiers_by_target.items()}
