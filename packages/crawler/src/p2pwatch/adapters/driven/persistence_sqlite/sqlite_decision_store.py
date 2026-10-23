"""``SqliteDecisionStore``: the matcher's verdicts, appended per target, and their latest reads.

It stores what the domain ignores (data-model spec §3): ``decided_at`` and ``node_id``, given
by the caller at each write.
"""

import sqlite3
from datetime import datetime

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord, MatchDecision
from p2pwatch.adapters.driven.persistence_sqlite.canonical_native_id import (
    require_canonical_native_id,
)
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction

# The tier column's value on a retraction's row.
_RETRACTED_TIER = "retracted"

_INSERT_DECISION = """
INSERT INTO match_decisions (file_id, target_id, rule_name, tier, decided_at, node_id)
VALUES (?, ?, ?, ?, ?, ?)
"""

# Latest verdict per (file_id, target_id) for one file (set-diff anti-redundancy, spec §7).
# ROW_NUMBER per target, order (decided_at, id) DESCENDING (most recent = rank 1); keep rank 1.
# INCLUDES a target whose latest tier is 'retracted' (no tier filter); EXCLUDES the legacy
# target_id='' sentinel (not a real target). The idx_match_decisions_file_target_decided index
# serves the filter.
_SELECT_LATEST_DECISIONS = """
SELECT target_id, rule_name, tier FROM (
    SELECT
        target_id, rule_name, tier,
        ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY decided_at DESC, id DESC) AS rn
    FROM match_decisions
    WHERE file_id = ? AND target_id <> ''
) WHERE rn = 1
"""

# Latest verdict per (file_id, target_id), kept when tier=download (download spec §5,
# multi-target §6). Window: ROW_NUMBER per (file_id, target_id), order (decided_at, id)
# DESCENDING (most recent = rank 1); keep rank 1 AND tier='download'. PARTITION BY the FULL
# key so a whole-episode file with BOTH segments in download yields BOTH candidates. Sorted
# by (network, native_id, target_id).
_SELECT_DOWNLOAD_DECISIONS = """
SELECT f.network, f.native_id, d.target_id FROM (
    SELECT
        file_id, target_id, tier,
        ROW_NUMBER() OVER (
            PARTITION BY file_id, target_id ORDER BY decided_at DESC, id DESC
        ) AS rn
    FROM match_decisions
) AS d
JOIN files AS f ON f.file_id = d.file_id
WHERE d.rn = 1 AND d.tier = 'download'
ORDER BY f.network, f.native_id, d.target_id
"""


class SqliteDecisionStore(DecisionWriter, DecisionReader):
    """SQLite implementation of the decisions' ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_decision(
        self, file: FileKey, decision: MatchDecision, decided_at: datetime, node_id: str
    ) -> None:
        """INSERT alone (autocommit); unknown file → FK violated → ``PersistenceError``.

        Only the 3 columns of ``MatchDecision`` are persisted (engine spec);
        ``explanation`` is runtime explainability, NEVER a column.
        """
        require_canonical_native_id(file)
        with wrap_sqlite_errors():
            self._connection.execute(
                _INSERT_DECISION,
                (
                    file.file_id,
                    decision.target_id,
                    decision.rule_name,
                    decision.tier,
                    utc_iso(decided_at),
                    node_id,
                ),
            )

    def record_retraction(
        self, file: FileKey, target_id: str, decided_at: datetime, node_id: str
    ) -> None:
        """Appends a per-target ``retracted`` decision (spec §7).

        Mirrors ``record_decision`` (same canonical-hash guard, same autocommit ``INSERT``): a
        file that no longer matches ``target_id`` gets an appended
        ``(target_id, rule_name="", tier=_RETRACTED_TIER)`` row instead of a mutation, per the
        append-only invariant. Retracting one target leaves the file's other targets intact.
        Unknown file → FK violated → ``PersistenceError``.
        """
        require_canonical_native_id(file)
        with wrap_sqlite_errors():
            self._connection.execute(
                _INSERT_DECISION,
                (
                    file.file_id,
                    target_id,
                    "",
                    _RETRACTED_TIER,
                    utc_iso(decided_at),
                    node_id,
                ),
            )

    def read_latest_decisions(self, file: FileKey) -> dict[str, FileTargetDecision]:
        """Latest verdict per target for this file (set-diff anti-redundancy, spec §7), READ.

        Maps ``target_id`` → its latest decision. INCLUDES a target whose latest decision is a
        :class:`Retraction` (the application's set-diff skips re-retracting it); EXCLUDES the
        legacy ``target_id=""`` sentinel. The hash is NOT validated canonical (harmless read: a
        non-canonical hash matches nothing → ``{}``).
        """
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT_LATEST_DECISIONS, (file.file_id,)).fetchall()
        return {row[0]: _file_target_decision(*row) for row in rows}

    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        """``(file, target_id)`` whose LATEST verdict is tier=download, to replay (download §5).

        Keyed per ``(file, target_id)``: a whole-episode file matching both segments now yields
        MULTIPLE :class:`DownloadCandidate` for the SAME file (one per target). READ.
        """
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT_DOWNLOAD_DECISIONS).fetchall()
        return tuple(
            DownloadCandidate(file=FileKey(Network(row[0]), row[1]), target_id=row[2])
            for row in rows
        )


def _file_target_decision(target_id: str, rule_name: str, tier: str) -> FileTargetDecision:
    if tier == _RETRACTED_TIER:
        return Retraction(target_id)
    return DecisionRecord(target_id, rule_name, DecisionTier(tier))
