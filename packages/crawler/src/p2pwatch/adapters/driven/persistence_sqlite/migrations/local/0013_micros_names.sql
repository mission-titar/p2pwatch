-- local.db, migration 0013: started_at carries its unit (micros spec, D1).
-- RENAME COLUMN rewrites the schema and no row: no copy before it.

ALTER TABLE backoff_states RENAME COLUMN started_at TO started_at_micros;
