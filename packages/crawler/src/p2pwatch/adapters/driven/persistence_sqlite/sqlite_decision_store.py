"""``SqliteDecisionStore``: the matcher's verdicts, appended per target, and their latest reads."""

import sqlite3

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.canonical_native_id import (
    require_canonical_native_id,
)
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision, FileTargetDecision, Retraction

# The tier column's value on a retraction's row.
_RETRACTED_TIER = "retracted"

_INSERT_DECISION = """
INSERT INTO match_decisions (file_id, target_id, rule_name, tier, decided_at_micros, node_id)
VALUES (?, ?, ?, ?, ?, ?)
"""

# Latest verdict per (file_id, target_id) for one file (set-diff anti-redundancy, spec §7).
# ROW_NUMBER per target, order (decided_at_micros, id) DESCENDING (most recent = rank 1); keep
# rank 1. INCLUDES a target whose latest tier is 'retracted' (no tier filter); EXCLUDES the legacy
# target_id='' sentinel (not a real target). The idx_match_decisions_file_target_decided_at_micros
# index serves the filter.
_SELECT_LATEST_DECISIONS = """
SELECT target_id, rule_name, tier FROM (
    SELECT
        target_id, rule_name, tier,
        ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY decided_at_micros DESC, id DESC) AS rn
    FROM match_decisions
    WHERE file_id = ? AND target_id <> ''
) WHERE rn = 1
"""

# Latest verdict per (file_id, target_id), kept when tier=download (download spec §5,
# multi-target §6). Window: ROW_NUMBER per (file_id, target_id), order (decided_at_micros, id)
# DESCENDING (most recent = rank 1); keep rank 1 AND tier='download'. PARTITION BY the FULL
# key so a whole-episode file with BOTH segments in download yields BOTH candidates. Sorted
# by (network, native_id, target_id).
_SELECT_DOWNLOAD_DECISIONS = """
SELECT f.network, f.native_id, d.target_id FROM (
    SELECT
        file_id, target_id, tier,
        ROW_NUMBER() OVER (
            PARTITION BY file_id, target_id ORDER BY decided_at_micros DESC, id DESC
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

    def record_decision(self, dated_decision: DatedDecision[FileTargetDecision]) -> None:
        """INSERT alone (autocommit); unknown file → FK violated → ``PersistenceError``.

        A retraction is the row ``(target_id, rule_name="", tier=_RETRACTED_TIER)``, appended
        instead of a mutation, per the append-only invariant (spec §7).
        """
        require_canonical_native_id(dated_decision.file)
        with wrap_sqlite_errors():
            self._connection.execute(
                _INSERT_DECISION,
                (
                    dated_decision.file.file_id,
                    *_decision_columns(dated_decision.decision),
                    instant_to_micros(dated_decision.decided_at),
                    dated_decision.node_id,
                ),
            )

    def read_latest_decisions(self, file: FileKey) -> dict[TargetId, FileTargetDecision]:
        """Latest verdict per target for this file (set-diff anti-redundancy, spec §7), READ.

        Maps ``target_id`` → its latest decision. INCLUDES a target whose latest decision is a
        :class:`Retraction` (the application's set-diff skips re-retracting it); EXCLUDES the
        legacy ``target_id=""`` sentinel. The hash is NOT validated canonical (harmless read: a
        non-canonical hash matches nothing → ``{}``).
        """
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT_LATEST_DECISIONS, (file.file_id,)).fetchall()
        decisions = [
            _file_target_decision(TargetId(row["target_id"]), row["rule_name"], row["tier"])
            for row in rows
        ]
        return {decision.target_id: decision for decision in decisions}

    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        """``(file, target_id)`` whose LATEST verdict is tier=download, to replay (download §5).

        Keyed per ``(file, target_id)``: a whole-episode file matching both segments now yields
        MULTIPLE :class:`DownloadCandidate` for the SAME file (one per target). READ.
        """
        with wrap_sqlite_errors():
            rows = self._connection.execute(_SELECT_DOWNLOAD_DECISIONS).fetchall()
        return tuple(
            DownloadCandidate(
                file=FileKey(Network(row["network"]), row["native_id"]),
                target_id=TargetId(row["target_id"]),
            )
            for row in rows
        )


def _decision_columns(decision: FileTargetDecision) -> tuple[str, str, str]:
    if isinstance(decision, Retraction):
        return decision.target_id, "", _RETRACTED_TIER
    return decision.target_id, decision.rule_name, decision.tier.value


def _file_target_decision(target_id: TargetId, rule_name: str, tier: str) -> FileTargetDecision:
    if tier == _RETRACTED_TIER:
        return Retraction(target_id)
    return DecisionRecord(target_id, rule_name, DecisionTier(tier))
