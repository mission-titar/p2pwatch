-- migration: copy-before
-- local.db, migration 0010: a waiting reason (descriptive names spec, D5).

UPDATE downloads SET waiting_reason = 'local_processing'
WHERE waiting_reason = 'local';
