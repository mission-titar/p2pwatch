# A monotone catalog: one range model for search observations and sources

- Date: 2026-10-13 (discussion 2026-10-12 and 2026-10-13)
- Status: DRAFT. A record of the Discuss phase's decisions, not yet a spec: no block table, no spec review,
  no operator approval of this file.
- Tier: Spec (catalog.db's schema and invariant, a migration of the node's history, the writers, `merge`,
  the webui's readers)
- Corrects: `agents/specs/2026-10-11-stage4-source-history.md` (stage 4, not merged), D4, D5 and D6
- Evidence:
  - a read-only snapshot of the node's catalog on 2026-10-12 (`sqlite3 .backup`, schema version 5, 4.1.0):
    `file_observations` holds 12,444,353 rows, 11,979 distinct variants, one node, two keywords, from
    2026-07-04T04:30Z to 2026-10-12T19:57Z (100.6 days). Every count in section 4 is computed on it by a
    one-pass script over the rows sorted by variant then time; the scripts are not kept;
  - aMule at the pinned commit `909d304d993ee07df6c6f6acf501a6d791d53666` (upstream, tag `v3.1.0`), read with
    `git show 909d304d9:<path>`;
  - AirDC++ Web Client's source, `master`, read on 2026-10-13: `airdcpp-webapi/api/OnlineUserUtils.cpp`,
    `airdcpp-webapi/api/common/Serializer.cpp`, `airdcpp-core/airdcpp/hub/ClientManager.cpp`.

## At a glance

```
files ──┬──< match_decisions
        ├──< observation_variants ──< observation_ranges
        └──< source_variants ──┬──< source_ranges
                 │             │
     sources >───┘ (optional)  └──< source_received_bytes
```

- **The invariant changes from "append-only" to "monotone"**: no row is deleted, and the one column an
  update may change is a range's `last_seen_at`, never downward. An append-only table is the case without
  that column.
- **Search observations become ranges**, like sources: 12.4M points become 918k ranges on the node's history.
- **`merge` becomes a plain union and never refuses**: the stage 4 limit on diverged copies disappears.
- **A range extends only while the thing was seen at the previous read, and never across more than a ceiling.**

## 1. Context and goals

Stage 4 stores sources as ranges updated in place, guarded by a trigger whose third rule ("no later range of
the same variant and node") makes `merge` refuse, for good, a copy diverged from a restored catalog (stage 4,
D6). Search observations stay points: 20.5 B each, about 0.9 GB a year at the node's pace. The backlog's
"Search observations as time ranges" asks to bring them in line.

Goals:

- **One model for both**: variants that hold properties, ranges that hold presence.
- **Safe by design, merge included**: a database that refuses every write that rewrites the past, and a
  merge that is commutative, idempotent and never refuses.
- **Compact**: a row per change, not a row per read.

## 2. Non-goals

- **No file-level byte count.** aMule cannot say "this file received N bytes from this source" (D6).
- **No identity for an NMDC source** (D7).
- **No retention bound**, as before.
- **No new network.** Stage 5's clients are named where a decision depends on them.

## 3. Decisions

### D1. The invariant: a monotone catalog

- No `DELETE` on any catalog table.
- `files`, `match_decisions`, `sources`, `observation_variants`, `source_variants` and
  `source_received_bytes`: no `UPDATE` (append-only, as today).
- `observation_ranges` and `source_ranges`: an `UPDATE` raises unless every column but `last_seen_at` is
  unchanged and `last_seen_at` is not lower than before. A no-op update passes (SQLite fires `BEFORE UPDATE`
  for an upsert's no-op `DO UPDATE`).
- *Reason: what makes `merge` safe is that every write moves the state up and the merge takes the union or
  the MAX. Append-only points are the trivial case. Stage 4's third rule encoded the writer's order, not the
  data's growth: true for the writer, false for a merge, and a trigger cannot tell who writes. It moves into
  the writer's statement (D4). The rules left are local to the row and true for every writer.*

### D2. Variants hold properties, ranges hold presence

```sql
CREATE TABLE observation_variants (
    variant_id INTEGER PRIMARY KEY,
    file_id BLOB NOT NULL REFERENCES files (file_id),
    filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    media_length_sec INTEGER,
    bitrate_kbps INTEGER,
    raw_meta TEXT NOT NULL,
    keyword TEXT NOT NULL,
    channel TEXT,
    content_hash BLOB NOT NULL UNIQUE
);

CREATE TABLE observation_ranges (
    variant_id INTEGER NOT NULL REFERENCES observation_variants (variant_id),
    node_id TEXT NOT NULL,
    first_seen_at INTEGER NOT NULL,
    source_count INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY (variant_id, node_id, first_seen_at, source_count),
    CHECK (last_seen_at >= first_seen_at)
) WITHOUT ROWID;

CREATE TABLE source_ranges (
    variant_id INTEGER NOT NULL REFERENCES source_variants (variant_id),
    node_id TEXT NOT NULL,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY (variant_id, node_id, first_seen_at),
    CHECK (last_seen_at >= first_seen_at)
) WITHOUT ROWID;
```

`sources` and `source_variants` are stage 4's, unchanged. `observations` (the points) is dropped by the
migration (D9).

- **`node_id` leaves `observation_variants` for the range**, as stage 4 does for sources. *Reason: a variant
  is a set of observed properties, which two nodes share; the observer belongs to the range.*
- **`channel` joins the search variant** (`ed2k` or `kad` on eD2k; `NULL` for the migrated history, which
  did not record it). *Reason: one search task runs per (keyword, channel), and the two channels' source
  counts measure different things (a server's count, Kad's). Without the channel, one variant fed by both
  alternates its state and opens a range at every read; D4's rule also needs one variant per task. It
  shows, as a bonus, a file visible on Kad and not on the servers.* The network stays on `files`: a result
  belongs to its file's network, and a channel only means something inside it.
- **A range column is either the key, `last_seen_at`, or a state fixed for the range's life.** A property
  with a small, stable domain goes in the variant (`role`, five values); an open-ended measure goes in the
  range as a state (`source_count`), so that it does not copy the variant's `filename` and `raw_meta` per
  value. A different state opens a new range.
- **The state is in the primary key.** *Reason: two ranges with the same start and a different state can
  only come from two writers under one `node_id` (D10); with the state in the key both rows survive a merge,
  where a key without it would keep one and silently drop the other.*
- *Reason for `source_count` as a state and not a min/max pair: its history is kept exactly and the trigger
  stays one rule, for 23% more ranges (section 4).*

### D3. What a range says

A range says: this node read this variant with this state at every read of its task from `first_seen_at` to
`last_seen_at`, and no two consecutive reads in it are further apart than the ceiling (D5). A gap between two
ranges says "not seen", never "absent": a search returns part of what exists, and a source list can miss a
peer for a round.

### D4. The writer extends the latest range by construction

The writer never names a range by its key. It extends "the latest" in one statement, and inserts when the
statement touches no row:

```sql
UPDATE source_ranges SET last_seen_at = :read_at
WHERE variant_id = :variant AND node_id = :node
  AND first_seen_at = (SELECT MAX(first_seen_at) FROM source_ranges
                       WHERE variant_id = :variant AND node_id = :node)
  AND last_seen_at >= :previous_read_at          -- seen at the previous read (D5)
  AND last_seen_at < :read_at
  AND :read_at - last_seen_at <= :ceiling;        -- D5
-- no row touched: INSERT a range (first_seen_at = last_seen_at = :read_at)
```

`observation_ranges` adds `source_count = :source_count` to the outer `WHERE`, and its `MAX` is taken over the
variant and node whatever the state, so that a change of state opens a range instead of extending an older one.

*Reason: no Python code can then target an older range; the guard stage 4's third rule gave lives in the one
statement the writer runs, and `merge`, which runs its own, is not bound by it.*

### D5. Extension: seen at the previous read, within a ceiling

A reading extends the latest range when both hold:

1. **the variant was seen at the task's previous read**: `last_seen_at >= previous_read_at`, where
   `previous_read_at` is the timestamp the same task stamped on its previous read. A task is a search task
   (keyword, channel) for search observations, and a download's sources read for sources. It is held in
   memory; after a restart there is none, so the first read opens new ranges, and the gap shows the time the
   crawler was down;
2. **the gap is within the ceiling**: `read_at - last_seen_at <= ceiling`. The ceiling is a resolution the
   catalog promises, a constant per table, the same on every node: **10 minutes for search observations, 2
   minutes for sources**.

- *Reason for rule 1: since stage 2 a search's cadence is not a setting. The adapter paces each channel (60 s
  between two starts, plus the search's length), so it moves with the number of keywords and the searches'
  length; a time tolerance would cut every range once the cadence passes it. "Seen at the previous read" has
  no threshold and ignores jitter. It is not a count over the N previous searches, which the operator found
  too complex: one timestamp per task.*
- *Reason for rule 2: rule 1 alone extends across any spacing. A range read every 3 minutes and one read every
  15, or one bridging an amuleapi outage (the previous successful read predates it), would say the same.*
- *Reason for no missed read tolerated (stage 4 tolerated one): an absence is information, and the reader can
  add a tolerance when it displays (D10); the stored data keeps every gap.*
- *Reason for constants and not settings: two nodes' ranges, merged, must mean the same thing.*
- If the cadence outgrows the ceiling (many keywords), ranges shrink to single reads: honest, at the cost of
  compactness.
- The values are chosen from the node's search cadence (section 4: 88% of gaps between 4 and 6 minutes) and
  stage 4's 30 s download poll. The sources' value is checked on the node's gap histogram once it runs a
  source writer (section 7).

### D6. Bytes received from a source: `source_received_bytes`

```sql
CREATE TABLE source_received_bytes (
    variant_id INTEGER NOT NULL REFERENCES source_variants (variant_id),
    node_id TEXT NOT NULL,
    read_at INTEGER NOT NULL,
    received_total INTEGER NOT NULL,
    PRIMARY KEY (variant_id, node_id, read_at),
    CHECK (received_total >= 0)
) WITHOUT ROWID;
```

- **One row per read where the source is `sending`.** Append-only. `source_ranges` loses `received_bytes` and
  `transfer_counter`.
- **`received_total` is the client's counter, opaque: only its differences mean something.** On eD2k it is
  `downloaded_bytes_session`, aMule's `CUpDownClient::m_nTransferredDown`: a member of the client object
  (`src/updownclient.h:861`), set to 0 only when the object is created (`src/BaseClient.cpp:196`), and grown
  by the bytes written into whichever file the client sends us (`src/DownloadClient.cpp:1022`). It counts
  every file received from that client. A drop means aMule recreated the client.
- **Displayed per source, never per file.** The source page shows what was received from it over time, its
  rate and its jitter, and its sessions; the file page shows who sent the file and when, from its ranges. *Reason:
  aMule cannot say what one file received from one source; the counter is honest at the source's level and
  can lie at the file's. A stage 5 client with a per-transfer counter may add the file then; it is not
  planned now.*
- **Keyed by the variant, not by `source_id`**, and grouped per source on display (by `source_id` across its
  variants, by name without one). *Reason: a source recorded without `source_id` (NMDC, D7) can send us a file;
  a `source_id` key could not hold its bytes, a break known today and not a speculative improvement. The
  ranges already identify a source this way (stage 4, D4).*
- *Reason for points and not a range column: as a range state, the counter would open a range at every read
  of a sending source and, being client-wide, on the source's `standby` ranges of our other files too. Its
  cost is bounded by the download slots: a source sending for 24 h is 2,880 rows, about 60 KB.*
- On eD2k a source that sends has a `source_id`: no opcode but the hello is accepted before the handshake
  (`src/ClientTCPSocket.cpp:341-342`), and the user hash is set during it (`SetUserHash`,
  `src/BaseClient.cpp:489`).

### D7. NMDC sources keep no identity

Stage 4's D2 stands: an NMDC source has no `source_id`, and is followed by its nick as `name`.

- AirDC++'s API exposes no "registered" status for a hub user. Its properties are `nick`, `share_size`,
  `description`, `tag`, `upload_speed`, `download_speed`, `ip4`, `ip6`, `email`, `file_count`,
  `hub_session_id`, `hub_url`, `hub_name`, `supports`, `flags`, `cid`, `upload_slots`
  (`OnlineUserUtils.cpp`); its flags `bot`, `favorite`, `ignored`, `self`, `nmdc`, `asch`, `offline`, `ccpm`,
  `away`, `op`, `hidden`, `noconnect`, `passive` (`Serializer.cpp`). An identity for registered nicks only
  cannot be built.
- The `cid` of an NMDC user is made locally, `Tiger(lower(nick) + lower(hub_url))`
  (`ClientManager::makeNmdcCID`): the umbrella's (nick, hub) pair, hashed, not an identity the user carries.
- *Reason (operator, 2026-10-13): an eD2k user hash is a random 128-bit number per installation, an NMDC nick
  a chosen word, often a client's default; making it a source would give both the same standing.*

### D8. `merge`

- Variants, `files`, `sources`, `match_decisions`, `source_received_bytes`: `INSERT OR IGNORE` (variants on
  `content_hash`, the others on their key, `source_received_bytes` with the variant remapped through
  `content_hash`).
- Ranges: inserted with the variant remapped through `content_hash`; on the same key,
  `last_seen_at = MAX(last_seen_at, excluded.last_seen_at)`. No `ORDER BY`, no `WHERE`.
- *Reason: every column but `last_seen_at` is in the key or fixed, and `MAX` is commutative and idempotent,
  so the merge is order-independent and re-runnable for every input, diverged copies included. The
  backlog's "Merge diverged copies of one node's catalog" is closed by it, and
  `test_merger.py::test_a_copy_diverged_from_a_restored_catalog_is_refused_whole` turns into its opposite.*

### D9. Migrating the node's history

- **Before any migration that rewrites data, an automatic copy**, `catalog.db.pre-<NNNN>-<UTC timestamp>`, next
  to the catalog, made with `VACUUM INTO` (consistent and compact). The docs keep recommending a backup; the
  copy means nothing is lost unless the operator deletes it. It needs the free space of a second catalog
  (5.8 GB on the node today): the migration refuses, naming the need, when it is missing. *Reason (operator,
  2026-10-13): a required backup is a step an operator skips; an automatic one is not.*
- **Search points become ranges with a time tolerance of 7.5 minutes** (1.5 x the history's 300 s cycle),
  cut also when `source_count` changes; `channel` is `NULL`. D5's rule 1 cannot apply, since the history did
  not record when searches ran.
  - *Reason for 7.5 minutes: the gap histogram (section 4) has its normal peak at 4 to 6 minutes and its "one
    search missed" peak at 9 to 11; the cut belongs in the trough between them. 10 minutes (2 x) sits on the
    second peak and would absorb most missed searches.*
- **Variants are re-keyed without `node_id`**: variants that differed only by node become one, their ranges
  keep their node.
- **What is lost**: only the exact instants inside a range. Every appearance, disappearance and change of
  `source_count` is kept, and no range spans a gap over 7.5 minutes, so the migration asserts no presence the
  points did not.
- **The node is at schema version 5**, so stage 1's migrations (0006 to 0009) and stage 4's (0010) run first.
  The copy taken before the first of them covers them all.
- **Stage 4's `source_ranges`**: its `received_bytes` and `transfer_counter` are dropped. No node holds a
  source range today (the stage 4 stack is not merged).

### D10. Reading ranges

- **Two ranges of one (variant, node, state) may overlap** only when two crawlers ran under one `node_id`: the
  default `node_id` is a UUID4 drawn into `local.db` (`local_state_repository.py:43`), so a copied `data/`
  directory starts a twin. No reader sums durations today (they count, and take the latest `last_seen_at`).
  **A reader that sums presence durations merges overlapping ranges first.**
- **The webui says "not seen" for a gap, never "absent"** (D3), and may join ranges across a gap it chooses to
  tolerate: a display choice, not stored.
- **Stage 4's per-range Received and Rate columns move to the source page**, computed from
  `source_received_bytes` (`webui/domain/format.py:93` computes the rate today).
- **`sightings.py`**, the one reader of search observations, reads ranges.

### D11. A clock that steps back

A reading with `read_at <= last_seen_at` of its latest range is dropped whole: no range touched, no
`source_received_bytes` row, so that no rate is computed over a negative interval. A warning is logged, so
that a clock step shows as one and not as an absence. *Reason (operator, 2026-10-13): marginal in likelihood
and impact; a step back on an NTP-synced host is seconds. Inserting a range in the past would break the
"latest range" order the writer relies on.*

## 4. Measurements (the node, 2026-10-12)

Gap between two consecutive sightings of one search variant (12.4M gaps):

| Gap | Share | Reading |
|---|---|---|
| under 1 min | 2.9% | the same variant twice in one cycle |
| 4 to 6 min | 87.5% | consecutive searches |
| 6 to 9 min | 2.0% | trough |
| 9 to 11 min | 2.5% | one search missed |
| 14 to 16 min, 19 to 21 min, ... | | two, three, ... missed |
| 30 min and more | 1.7% | |

Rows for the search history, by storage:

| Storage | Rows |
|---|---|
| points (today) | 12,444,353 |
| ranges, tolerance 7.5 min, cut on `source_count` (D9) | 917,834 |
| ranges, tolerance 10 min, cut on `source_count` | 677,652 |
| ranges, tolerance 30 min, cut on `source_count` | 268,468 |
| ranges, tolerance 30 min, `source_count` as min/max | 218,013 |
| fixed hourly buckets (rejected, section 5) | 1,270,390 |

`source_count` changes 71,469 times in 12.4M points; no variant has two points at one instant with two counts.

## 5. Alternatives rejected

- **Fixed-grid buckets** (key: variant, node, bucket start; `first`, `last`, `reads`, min and max as monotone
  columns). Their key does not depend on history, so a merge is always a column-wise MIN/MAX. Rejected: a
  bucket costs a row per slot of presence even when nothing changes (a source stable for a month: 720 hourly
  rows against one range), and a gap inside a slot shows only through `reads`.
- **Accumulator columns in ranges** (`received_bytes`, `transfer_counter`): moved to D6's points.
- **Range snapshots, append-only** (each extension inserts a row, readers take the MAX): as large as points,
  unless checkpoints are spaced, which loses a range's tail on a crash.
- **Points everywhere**: about 0.9 GB a year for search at the node's pace, and for sources about 1.5 GB a year
  at the 73 sources of 2026-10-11 polled every 30 s.
- **A tolerance in searches** ("present at one of the N previous searches"): needs to know which searches ran;
  D5's single timestamp does the same job.
- **(nick, hub) as an NMDC identity**: D7.

## 6. Adjacent backlog items

- **"Search observations as time ranges"**: this document.
- **"Merge diverged copies of one node's catalog"**: closed by D8.
- **"Paginate the file detail timeline"**: its 38,593 sightings for the heaviest file become far fewer ranges;
  whether it is still needed is measured after the migration.
- **"Sort the files view by first seen"**: `first_seen_at` becomes a range column; stays open.
- **Stage 5**: D6 and D7 name what its clients must be checked for (a per-transfer counter, an identity).

## 7. Open points for the Spec phase

- **Stage 4's order**: amend the unmerged stage 4 stack, or merge it as approved and land this as the next lot.
- **The sources' ceiling**: check 2 minutes against the gap histogram of `source_ranges` on the node, the
  measure stage 4's handoff already plans.
- **One `read_at` per search**: the repository stamps `observed_at` once per call
  (`catalog_repository.py:125`); D5 needs the search task to know that value for its next read.
- **The migration's budget** in the hardened container (2 GB memory, temp store), on the real catalog, as
  stage 1's spike did: the points are read in primary-key order (variant, then time), so one ordered scan
  suffices.
- **The docs**: "append-only" becomes "monotone" in `AGENTS.md`, `README.md`, `docs/index.md`,
  `docs/contributing/architecture.md` and `persistence_sqlite/__init__.py`; `docs/operate.md`'s merge
  paragraph loses its limit.
