-- local.db, migration 0017: the notifications left to send, one row per notification and service.
-- A notification's fields as a JSON object, its kind naming which.

CREATE TABLE pending_notifications (
    id INTEGER PRIMARY KEY,
    service_scheme TEXT NOT NULL,
    service_audience TEXT NOT NULL,
    service_ordinal INTEGER NOT NULL,
    kind TEXT NOT NULL,
    notification TEXT NOT NULL
) STRICT;
