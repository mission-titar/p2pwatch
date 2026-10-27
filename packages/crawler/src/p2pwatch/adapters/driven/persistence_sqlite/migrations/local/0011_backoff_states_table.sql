-- migration: copy-before
-- local.db, migration 0011: the search backoff in a typed table, each wait's start and delay.
-- The waits pending at the upgrade are dropped with scheduler_state: each restarts at its base.

CREATE TABLE backoff_states (
    client_name TEXT NOT NULL,
    channel TEXT,
    attempts INTEGER NOT NULL CHECK (attempts >= 1),
    started_at INTEGER NOT NULL,
    delay_seconds REAL NOT NULL CHECK (delay_seconds >= 0)
) STRICT;

-- On an expression: a unique constraint holds two NULL channels distinct.
CREATE UNIQUE INDEX idx_backoff_states_client_name_channel
ON backoff_states (client_name, COALESCE(channel, ''));

DROP TABLE scheduler_state;
