-- local.db, migration 0012: two columns take the code's names (names and other hexagons spec, D7).
-- RENAME COLUMN rewrites the schema and no row: no copy before it.

ALTER TABLE downloads RENAME COLUMN last_seen_at TO latest_seen_at;

ALTER TABLE downloads RENAME COLUMN last_progress_at TO latest_progress_at;
