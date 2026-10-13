-- local.db, migration 0009: the re-evaluation marker's names (descriptive names spec, D5).

ALTER TABLE backfill_state RENAME TO reevaluation_state;

ALTER TABLE reevaluation_state RENAME COLUMN policy_sha256 TO policy_fingerprint;
