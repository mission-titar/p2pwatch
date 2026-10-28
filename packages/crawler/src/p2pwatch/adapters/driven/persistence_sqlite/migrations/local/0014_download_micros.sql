-- migration: copy-before
-- local.db, migration 0014: the downloads' stamps as micros, in a STRICT table (micros spec, D1).
-- iso_to_micros fails on a NULL, hence the CASE on each nullable stamp.

-- 1. Renamed away; downloads has no trigger, no named index, and no table references it.
ALTER TABLE downloads RENAME TO downloads_old;

-- 2. The new table under its final name.
CREATE TABLE downloads (
    file_id BLOB PRIMARY KEY,
    network TEXT NOT NULL,
    native_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    state TEXT NOT NULL,
    queued_at_micros INTEGER NOT NULL,
    completed_at_micros INTEGER,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    latest_seen_at_micros INTEGER,
    bytes_done INTEGER,
    latest_progress_at_micros INTEGER,
    waiting_reason TEXT,
    failure_reason TEXT,
    UNIQUE (network, native_id),
    CHECK (network IN ('ed2k')),
    CHECK (network <> 'ed2k' OR (LENGTH(native_id) = 32 AND native_id NOT GLOB '*[^0-9a-f]*'))
) STRICT;

-- 3. Copy.
INSERT INTO downloads (
    file_id,
    network,
    native_id,
    target_id,
    state,
    queued_at_micros,
    completed_at_micros,
    size_bytes,
    latest_seen_at_micros,
    bytes_done,
    latest_progress_at_micros,
    waiting_reason,
    failure_reason
)
SELECT
    file_id,
    network,
    native_id,
    target_id,
    state,
    ISO_TO_MICROS(queued_at) AS queued_at_micros,
    CASE
        WHEN completed_at IS NULL THEN NULL ELSE ISO_TO_MICROS(completed_at)
    END AS completed_at_micros,
    size_bytes,
    CASE
        WHEN latest_seen_at IS NULL THEN NULL ELSE ISO_TO_MICROS(latest_seen_at)
    END AS latest_seen_at_micros,
    bytes_done,
    CASE
        WHEN latest_progress_at IS NULL THEN NULL ELSE ISO_TO_MICROS(latest_progress_at)
    END AS latest_progress_at_micros,
    waiting_reason,
    failure_reason
FROM downloads_old;

-- 4. The old table.
DROP TABLE downloads_old;
