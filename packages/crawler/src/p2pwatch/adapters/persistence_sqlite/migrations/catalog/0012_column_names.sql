-- catalog.db, migration 0012: three columns take the code's names (descriptive names spec, D5).
-- RENAME COLUMN rewrites the schema, its triggers and CHECKs, and no row: no copy before it.

ALTER TABLE source_observations RENAME COLUMN transfer_counter TO session_received_bytes;

ALTER TABLE source_variants RENAME COLUMN directly_reachable TO connectable;

ALTER TABLE observation_variants RENAME COLUMN media_length_sec TO duration_seconds;
