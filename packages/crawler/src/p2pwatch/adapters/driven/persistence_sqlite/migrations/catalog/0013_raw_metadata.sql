-- catalog.db, migration 0013: raw_meta takes the code's name (names and other hexagons spec, D7).
-- RENAME COLUMN rewrites the schema, its triggers and CHECKs, and no row: no copy before it.

ALTER TABLE observation_variants RENAME COLUMN raw_meta TO raw_metadata;

ALTER TABLE source_variants RENAME COLUMN raw_meta TO raw_metadata;
