-- migration: copy-before
-- catalog.db, migration 0011: sources as variants and points, every table append-only again
-- (source points spec, D1, D2, D8). Stage 4's source rows are dropped: no release holds them.

DROP TABLE source_ranges;

DROP TABLE source_variants;

CREATE TABLE source_variants (
    variant_id INTEGER PRIMARY KEY,
    file_id BLOB NOT NULL REFERENCES files (file_id),
    source_id BLOB REFERENCES sources (source_id),
    name TEXT,
    software TEXT,
    role TEXT NOT NULL,
    contact_point TEXT,
    directly_reachable INTEGER,
    raw_meta TEXT NOT NULL,
    node_id TEXT NOT NULL,
    content_hash BLOB NOT NULL UNIQUE,
    CHECK (role IN ('sending', 'queued', 'nothing_new', 'standby', 'undetermined')),
    CHECK (directly_reachable IN (0, 1))
) STRICT;

CREATE INDEX idx_source_variants_file_source ON source_variants (file_id, source_id);
CREATE INDEX idx_source_variants_source_id ON source_variants (source_id);
CREATE INDEX idx_source_variants_name ON source_variants (name);
CREATE INDEX idx_source_variants_node_id ON source_variants (node_id);

CREATE TABLE source_observations (
    variant_id INTEGER NOT NULL REFERENCES source_variants (variant_id),
    observed_at INTEGER NOT NULL,
    transfer_counter INTEGER NOT NULL,
    PRIMARY KEY (variant_id, observed_at),
    CHECK (transfer_counter >= 0),
    -- The micros of datetime.min and datetime.max in UTC, the instants micros_to_instant reads.
    CHECK (observed_at BETWEEN -62135596800000000 AND 253402300799999999)
) STRICT, WITHOUT ROWID;

CREATE TRIGGER source_variants_no_update
BEFORE UPDATE ON source_variants
BEGIN
    SELECT RAISE(ABORT, 'source_variants is append-only');
END;

CREATE TRIGGER source_variants_no_delete
BEFORE DELETE ON source_variants
BEGIN
    SELECT RAISE(ABORT, 'source_variants is append-only');
END;

CREATE TRIGGER source_observations_no_update
BEFORE UPDATE ON source_observations
BEGIN
    SELECT RAISE(ABORT, 'source_observations is append-only');
END;

CREATE TRIGGER source_observations_no_delete
BEFORE DELETE ON source_observations
BEGIN
    SELECT RAISE(ABORT, 'source_observations is append-only');
END;
