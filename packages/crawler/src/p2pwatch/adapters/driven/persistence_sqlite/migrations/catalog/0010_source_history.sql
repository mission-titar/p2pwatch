-- catalog.db, migration 0010: the sources of our downloads as time ranges (stage 4 spec, D2 to D5).
-- Each CHECK follows D17's rule: a column something depends on, stated by the row alone, stable.

CREATE TABLE sources (
    source_id BLOB PRIMARY KEY,
    network TEXT NOT NULL,
    native_id TEXT NOT NULL,
    UNIQUE (network, native_id),
    CHECK (network IN ('ed2k')),
    CHECK (network <> 'ed2k' OR (LENGTH(native_id) = 32 AND native_id NOT GLOB '*[^0-9a-f]*'))
);

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
    content_hash BLOB NOT NULL UNIQUE,
    CHECK (role IN ('sending', 'queued', 'nothing_new', 'standby', 'undetermined'))
);

CREATE INDEX idx_source_variants_file_source ON source_variants (file_id, source_id);
CREATE INDEX idx_source_variants_source_id ON source_variants (source_id);
CREATE INDEX idx_source_variants_name ON source_variants (name);

CREATE TABLE source_ranges (
    variant_id INTEGER NOT NULL REFERENCES source_variants (variant_id),
    node_id TEXT NOT NULL,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    received_bytes INTEGER NOT NULL,
    transfer_counter INTEGER NOT NULL,
    PRIMARY KEY (variant_id, node_id, first_seen_at),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (received_bytes >= 0)
) WITHOUT ROWID;

CREATE TRIGGER sources_no_update
BEFORE UPDATE ON sources
BEGIN
    SELECT RAISE(ABORT, 'sources is append-only');
END;

CREATE TRIGGER sources_no_delete
BEFORE DELETE ON sources
BEGIN
    SELECT RAISE(ABORT, 'sources is append-only');
END;

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

-- An update that changes nothing passes: merge's upsert meets a closed range again (D5, D6).
CREATE TRIGGER source_ranges_only_grow
BEFORE UPDATE ON source_ranges
WHEN
    new.variant_id IS NOT old.variant_id
    OR new.node_id IS NOT old.node_id
    OR new.first_seen_at IS NOT old.first_seen_at
    OR new.last_seen_at < old.last_seen_at
    OR new.received_bytes < old.received_bytes
    OR new.transfer_counter < old.transfer_counter
    OR (
        (
            new.last_seen_at > old.last_seen_at
            OR new.received_bytes > old.received_bytes
            OR new.transfer_counter > old.transfer_counter
        )
        AND EXISTS (
            SELECT 1 FROM source_ranges AS later
            WHERE
                later.variant_id = old.variant_id
                AND later.node_id = old.node_id
                AND later.first_seen_at > old.first_seen_at
        )
    )
BEGIN
    SELECT RAISE(ABORT, 'source_ranges only grows its latest range');
END;

CREATE TRIGGER source_ranges_no_delete
BEFORE DELETE ON source_ranges
BEGIN
    SELECT RAISE(ABORT, 'source_ranges only grows its latest range');
END;
