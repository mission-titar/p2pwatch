-- local.db, migration 0016: each client's latest search start by channel and scope.

CREATE TABLE latest_search_starts (
    client_name TEXT NOT NULL,
    channel TEXT NOT NULL,
    scope TEXT NOT NULL,
    started_at_micros INTEGER NOT NULL,
    PRIMARY KEY (client_name, channel, scope)
) STRICT;
