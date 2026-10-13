-- local.db, migration 0010: the backoff key and a waiting reason (descriptive names spec, D5).

UPDATE scheduler_state SET key = 'backoff_states'
WHERE key = 'channel_backoff';

UPDATE downloads SET waiting_reason = 'local_processing'
WHERE waiting_reason = 'local';
