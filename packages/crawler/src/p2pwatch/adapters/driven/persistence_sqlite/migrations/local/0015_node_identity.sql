-- migration: copy-before
-- local.db, migration 0015: node_runtime becomes node_identity, every table STRICT (micros spec).
-- A node_id without its created_at reaches the NOT NULL and fails the migration (D7).

-- 1. The identity, one typed row; no code reads any other key of node_runtime.
CREATE TABLE node_identity (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    node_id TEXT NOT NULL,
    created_at_micros INTEGER NOT NULL
) STRICT;

INSERT INTO node_identity (id, node_id, created_at_micros)
SELECT
    1 AS id,
    node_id_row.value AS node_id,
    CASE
        WHEN created_at_row.value IS NULL THEN NULL ELSE ISO_TO_MICROS(created_at_row.value)
    END AS created_at_micros
FROM node_runtime AS node_id_row
LEFT JOIN node_runtime AS created_at_row ON created_at_row.key = 'created_at'
WHERE node_id_row.key = 'node_id';

DROP TABLE node_runtime;

-- 2. reevaluation_state rebuilt STRICT; no trigger, no named index, no table references it.
ALTER TABLE reevaluation_state RENAME TO reevaluation_state_old;

CREATE TABLE reevaluation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    policy_fingerprint TEXT NOT NULL
) STRICT;

INSERT INTO reevaluation_state (id, policy_fingerprint)
SELECT
    id,
    policy_fingerprint
FROM reevaluation_state_old;

DROP TABLE reevaluation_state_old;
