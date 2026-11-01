-- migration: copy-before
-- catalog.db, migration 0015: a decision's instant as micros, decided_at_micros (micros spec, D1).
-- Every row keeps its id, which breaks a tie between two decisions of one instant (D6).

-- 1. The old table's triggers and index (an index name survives a rename and would collide).
DROP TRIGGER match_decisions_no_update;
DROP TRIGGER match_decisions_no_delete;
DROP INDEX idx_match_decisions_file_target_decided;

-- 2. Renamed away; no table references match_decisions.
ALTER TABLE match_decisions RENAME TO match_decisions_old;

-- 3. The new table under its final name.
CREATE TABLE match_decisions (
    id INTEGER PRIMARY KEY,
    file_id BLOB NOT NULL REFERENCES files (file_id),
    target_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    tier TEXT NOT NULL,
    decided_at_micros INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    CHECK (tier IN ('catalog', 'notify', 'download', 'retracted')),
    -- The micros of datetime.min and datetime.max in UTC, the instants micros_to_instant reads.
    CHECK (decided_at_micros BETWEEN -62135596800000000 AND 253402300799999999)
) STRICT;

CREATE INDEX idx_match_decisions_file_target_decided_at_micros
ON match_decisions (file_id, target_id, decided_at_micros);

-- 4. Copy.
INSERT INTO match_decisions (
    id, file_id, target_id, rule_name, tier, decided_at_micros, node_id
)
SELECT
    id,
    file_id,
    target_id,
    rule_name,
    tier,
    ISO_TO_MICROS(decided_at) AS decided_at_micros,
    node_id
FROM match_decisions_old
ORDER BY id;

-- 5. The old table.
DROP TABLE match_decisions_old;

-- 6. The append-only triggers.
CREATE TRIGGER match_decisions_no_update
BEFORE UPDATE ON match_decisions
BEGIN
    SELECT RAISE(ABORT, 'match_decisions is append-only');
END;

CREATE TRIGGER match_decisions_no_delete
BEFORE DELETE ON match_decisions
BEGIN
    SELECT RAISE(ABORT, 'match_decisions is append-only');
END;
