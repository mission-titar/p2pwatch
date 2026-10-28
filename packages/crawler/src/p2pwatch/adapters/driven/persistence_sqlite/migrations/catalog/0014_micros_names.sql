-- catalog.db, migration 0014: both observed_at columns carry their unit (micros spec, D1).
-- RENAME COLUMN rewrites the schema, its triggers and CHECKs, and no row: no copy before it.

ALTER TABLE observations RENAME COLUMN observed_at TO observed_at_micros;

ALTER TABLE source_observations RENAME COLUMN observed_at TO observed_at_micros;
