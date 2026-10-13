# An append-only catalog again: sources as points

- Date: 2026-10-13 (discussion 2026-10-12 and 2026-10-13)
- Status: approved by the operator on 2026-10-13.
- Tier: Spec (catalog.db's schema and invariant, a config key, `merge`, the webui's readers)
- Replaces: the draft `agents/specs/2026-10-13-monotone-catalog-ranges.md` (commit `367e4df`), which turned
  search observations into ranges; the operator dropped ranges altogether (2026-10-13, section 5).
- Corrects: `agents/specs/2026-10-11-stage4-source-history.md` (stage 4, merged on 2026-10-12 as #177 to
  #192, in no release), D4, D5, D6 and D8, and the parts of D9, D12 and D13 that read ranges.
- Evidence:
  - the migration spike of 2026-10-13 on a snapshot of the node's catalog, in the core image `main` under
    `deploy/compose.yml`'s limits: `/home/geoffrey/Projets/p2pwatch-catalog-migration-spike-2026-10-13/`
    (`REPORT.md`, `scripts/`, `logs/`, the snapshot `snapshot-v5.db`);
  - the spec review of the draft (`.reviews/monotone-ranges-spec.md`, 2026-10-13), whose findings on the
    draft's D14 section 9 carries;
  - this repository at `ba32bc0` (`main`, 2026-10-13); paths under `packages/crawler/src/p2pwatch/` unless
    noted.

## At a glance

```
files ──┬──< match_decisions
        ├──< observation_variants ──< observations
        └──< source_variants ──< source_observations
                 │
     sources >───┘ (optional)
```

- **No ranges anywhere.** A variant holds the properties a node observed, `node_id` included; every read adds
  one point per variant seen. Sources follow the model search observations have had since stage 1.
- **catalog.db is append-only again, every table.** Stage 4's one exception, `source_ranges`, goes, and with
  it the limit that made `merge` refuse a diverged copy.
- **Sources are read every 5 minutes**, a new setting, instead of at every 30 s download poll.
- **Periods are computed when displayed**, never stored.

## 1. Context and goals

Stage 4 records the sources of our downloads as ranges updated in place, under a trigger whose third rule
("no later range of the same variant and node", `migrations/catalog/0010_source_history.sql:68-95`) makes
`merge` refuse, on every attempt, a copy diverged from a restored catalog (stage 4, D6). The draft this spec
replaces generalised ranges to search observations, and its review showed what ranges cost: a ceiling whose
value the catalog must promise forever, a writer bound to the latest range, a migration of the history.

What ranges were meant to save is small. After stage 1's variants, the node's 12,587,498 search points weigh
214 MB (the spike: `observations` holds 213,827,584 B of pages at version 10, `logs/07-v10-counts.log`), about
0.77 GB a year at 4.1.0's pace (one search cycle every 300 s); as ranges, 59 MB (the spike's
`observation_ranges`). Stage 2's pace, on `main`, is not measured yet (section 8).

Goals:

- **One model**: variants that hold properties, points that record a read.
- **Append-only, so merge-safe by construction**: a union of rows, commutative, idempotent, never refused for
  its content.
- **Volumes the webui can read**: sources at a resolution that keeps a long download's history small.

## 2. Non-goals

- **Search observations are unchanged**: their tables, writer and readers stay as stage 1 left them.
  (Corrected: their tables and writer are unchanged; the file page's "Observations" timeline is
  read within D6's interval, block 20, operator 2026-10-13.)
- **No retention bound**, as before.
- **No identity for an NMDC source**: stage 4's D2 stands. (The draft checked AirDC++'s API on 2026-10-13: it
  exposes no "registered" flag for a hub user, and an NMDC `cid` is a local hash of nick and hub.)
- **No new network.**
- **No copy before a migration**: designed in section 9, left to a lot of its own (operator, 2026-10-13), and
  required before the next release.
- **No release decided here**: Wrap proposes, the operator decides (`agents/workflow.md`, Wrap (f)).

## 3. Decisions

### D1. The invariant: append-only, every table

- No `UPDATE` and no `DELETE` on any catalog table, the `<table>_no_update` / `<table>_no_delete` triggers
  with `RAISE(ABORT, '<table> is append-only')`, as stage 1 wrote them.
- `AGENTS.md`'s Persistence row and every copy of the invariant lose stage 4's exception.
- *Reason: no table needs an update once every read is a point, and append-only is the rule `merge` was built
  on (MVP spec §11).*

### D2. Sources as points: `source_variants` and `source_observations`

```sql
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
    CHECK (role IN ('sending', 'queued', 'nothing_new', 'standby', 'undetermined'))
);

CREATE TABLE source_observations (
    variant_id INTEGER NOT NULL REFERENCES source_variants (variant_id),
    observed_at INTEGER NOT NULL,
    transfer_counter INTEGER NOT NULL,
    PRIMARY KEY (variant_id, observed_at),
    CHECK (transfer_counter >= 0)
) WITHOUT ROWID;
```

`sources` is stage 4's, unchanged. `source_variants` keeps stage 4's three indexes (`(file_id, source_id)`,
`(source_id)`, `(name)`) and gains one on `node_id`. Times are microseconds since the epoch, as everywhere.
(Corrected: the `node_id` index serves `has_points_before` only; D4's and D5's per-source reads write
`+v.node_id`, since without `ANALYZE` the planner took it and walked every variant of the node. Holistic
review.)

- **`node_id` moves into the variant**, as in `observation_variants`, and into its `content_hash`. *Reason: a
  point then holds an integer, a time and a counter, 23.9 B with its B-tree (the spec review's bench, `dbstat`);
  with `node_id` in the point, its 36 characters would double every row. One node writes one set of variants; a
  merged catalog holds each node's.*
- **`transfer_counter` is the client's byte counter at the read**, for every role: on eD2k
  `downloaded_bytes_session`, aMule's `GetTransferredDown()`, counting what we received from that client over
  all files, set to 0 when aMule creates the client (stage 4, D4). *Reason: the point stores what was read; which
  growth counts for a file is the reader's rule (D6). A counter that changes at every read is harmless in a
  point, where in a variant it would make one variant per read.*
- **One point per variant per read.** The primary key refuses a second point at one instant; the writer
  inserts with `ON CONFLICT (variant_id, observed_at) DO NOTHING`, never `OR IGNORE`, which would also swallow a
  `CHECK` (architecture.md §8.2). *Reason: the adapter already merges two rows of one identity in one reading (stage 4,
  D7), so a second point at one instant could only repeat the first.*
- **A clock that steps back writes points out of order**, and nothing breaks: no reader assumes the order of
  insertion, and no rule depends on the latest point but D4's carried role, which reads by time.
- *Reason for points over ranges: section 5.*

### D3. Sources are read every `download.sources_interval_seconds`

- **A new key, `download.sources_interval_seconds`, default 300**, a positive finite number like every number
  of `crawler.yml` (`adapters/config/crawler_config.py`, `_positive`). (Corrected: at most a day, 86,400, as every
  delay of `crawler.yml`, and 30 days for `lost_after_seconds` and `reappeared_after_seconds`, read by one
  helper; an unbounded value overflowed the tolerance in microseconds. Operator, 2026-10-13, on block 50's
  question.) The cycle's sources step
  (`application/run_download_cycle.py`, `_record_sources`) runs on a round when at least that long has passed
  since its last run; the first round after a start runs it. The time of the last run is held in memory.
- **The last run's time is taken when the step starts**, whether it ends well or on an unreachable client:
  a failed read is retried at the next interval, not at every round.
- **The reads' spacing** is taken as `sources_interval_seconds + poll_interval_seconds`: the step runs on the
  first round at least the interval after the last, and rounds come every poll plus the cycle's length, so two
  reads are between the interval and the interval plus a round apart. D4 and D6 derive their tolerance from
  it. (Corrected: D4 only; D6's tolerance is a webui setting, operator 2026-10-13.) *Reason: with the poll added, 3 x the spacing tolerates one missed read for any interval, as long as a
  cycle stays under half the spacing, which stage 4 already assumed of the poll.*
- *Reason (operator, 2026-10-13): at 30 s, the 52 source rows of stage 4's probe (34.5 on average) make 55M
  points a year,
  and a download kept for months, the common case for lost media, makes millions of points on one file, which
  the file page would read at every display. Every 5 minutes it is 5.5M points a year, about 0.13 GB, the order
  of the search observations; it is enough to recognise a recurring sharer, delays `new-source` by 5 minutes
  at worst, and cuts amuleapi's detail calls tenfold. A setting, not a constant: points are exact whatever
  their spacing, so two nodes reading at two intervals still mean the same thing. Their display does not
  (D6's limit).*

### D4. The writer

`record_readings(file, readings, read_at)` writes one download's readings in one transaction (stage 4's
`BEGIN IMMEDIATE`):

- a reading with neither identity nor name is dropped (stage 4, D4);
- its role, when the reading is in a passing state, is carried from the source's latest point on this file on
  this node (stage 4's identity: `(file_id, source_id)`, or `(file_id, name)` without a `source_id`), when that
  point is within the tolerance before `read_at` and its counter is not above the reading's; otherwise
  `undetermined` (stage 4, D3's table and `carried_role`, unchanged);
- the variant is inserted with `ON CONFLICT (content_hash) DO NOTHING`, as stage 4 does, then one point (D2);
- it returns, for each reading kept, its identity, name and role (a carried one included).

**The tolerance is 3 x the reads' spacing (D3)**, a gap equal to it included: 16.5 minutes at the defaults. *Reason: stage 4's rule, which
tolerated one missed read (`3 x poll_interval_seconds`, D4's reasons), carried over to the new spacing.*

`tolerance` leaves the port, `_TOLERATED_POLLS` leaves `run_download_cycle.py`: the repository derives the
tolerance from the spacing it is constructed with.

### D5. `new-source` and `reappeared` over points

The two notifications keep stage 4's meaning (its D9), read over points.

**Terms.**

- A **round** is one sources read: every D3 interval, the cycle reads the sources of each of our downloads, one
  download after the other, and writes their points.
- **`round_started_at`** is the moment a round begins, before its first download (`_AlertRound(deps.clock.now())`
  in `_record_sources`).
- A point is **useful** when its variant's role is `sending` or `queued`, **not useful** when it is
  `nothing_new` (stage 4, D3's groups). `standby` and `undetermined` are neither, and are ignored here.
- **Earlier** means on this node, on any file, with `observed_at < round_started_at`.

**The rule.** After a download's points are committed, for each reading of it that has a `source_id` and a useful
role (a carried one included), and whose source was not notified yet in this round:

1. the source has no earlier useful point: emit `new-source`;
2. otherwise, its latest earlier point that is useful or not useful is older than
   `download.reappeared_after_seconds` before `round_started_at`: emit `reappeared`, with that absence;
3. otherwise, nothing.

Stage 4's other rules stand: no event on the node's first round (no earlier point at all on this node), none for a
reading without `source_id`, emitted after the commit, at most once.

**Why `round_started_at`, not the time of the question.** The question is asked after the download's points are
written. Bob, never seen, is useful on file A: at 12:00:01 his point on A is written, then the question asked;
counted, that point would make Bob already known, and `new-source` would never be emitted. On file B, his point on
A would do the same. Cutting at `round_started_at` (12:00:00) keeps every point of the current round out, on every
file; the per-round set of notified sources stops a second event on B.

**The rule runs on every useful reading, with no memory between rounds.** A source useful at every round has, from
its second round on, an earlier useful point (so not `new-source`) and a recent one (so not `reappeared`): it is
notified once. `source_alerts.source_alert` keeps its rule.

**Two queries, one row read per variant.** For each variant of the source on this node:

- `EXISTS (SELECT 1 FROM source_observations WHERE variant_id = v.variant_id AND observed_at < :round_started_at)`,
  over its useful variants, answers step 1;
- `(SELECT MAX(observed_at) FROM source_observations WHERE variant_id = v.variant_id AND observed_at <
  :round_started_at)`, over its useful and not-useful variants, answers step 2.

The primary key `(variant_id, observed_at)` answers each by one seek. (Corrected: one statement answers
both, each variant's `MAX(observed_at)` before the round with its role, grouped in Python; a source decided
once is not asked again in the round, since the answer cuts at `round_started_at`. Block 10's report.) *Reason: a source read for a year has about
100k points. The join form, `MAX(o.observed_at)` over `source_variants JOIN source_observations`, plans as the same
`SEARCH` yet reads every earlier point of each variant (2.7 ms against 0.1 ms at a year, the spec review's bench),
so the plan alone does not tell them apart.*

### D6. The webui computes periods

The file page's "Source history", the source page and the name page show periods:

- **A period** joins consecutive points of one identity on one file and one node (stage 4's identity: the
  `source_id`, or the name without one), ordered by time, and is cut where the variant changes, where the gap
  passes the tolerance (D4's, from the same two keys of `crawler.yml`, which the composition passes to the
  webui), or where the counter drops. (Corrected: the tolerance is a reading option,
  `webui.source_period_gap_seconds` beside `webui.enabled`, a positive finite number like every number of
  `crawler.yml`, default 990, which is 3 x (300 + 30), the writer's tolerance at the shipped defaults. It
  exists in every run mode, so a crawl-only node, which reads no source, has one too; the composition
  passes it to the webui, which never reads the download section for it. Operator, 2026-10-13, on block
  10's question. Corrected again: at most a day, as D3's key, block 50.) It shows first and last seen,
  the variant's columns and its node.
  *Reason: joined per variant, `queued`, `sending`, `queued` would make one `queued` period over the `sending`
  one, and `sending`, `standby`, `sending` one `sending` period counting the bytes of the file the source sent
  meanwhile.*
- **The tolerance is the displaying node's**: a merged catalog holding a node that reads at another interval
  shows its reads cut by this node's tolerance, as one-point periods when that node reads more rarely.
  (Corrected: the displaying node's `webui.source_period_gap_seconds`, which its operator may raise for
  such a catalog.) An
  accepted limit (section 8): the points stay exact, and a merged catalog is read by its operator.
- **Received bytes**, on a `sending` period only, are the counter's growth from its first point to its last;
  the rate divides it by the period's length (`webui/domain/format.py`, `average_rate`). *Reason: stage 4's
  rule (D4's reasons: a source sends one file at a time, and a `standby` row's counter grows with another
  file).*
- **Over a time interval, at most 7 days** (operator, 2026-10-13): the file page's "Source history", and the
  source and name pages' period tables, compute their periods in SQL with window functions over the points
  read in the page's interval only, newest first. *Reason: over the whole history the cost grows with it: 8.6 s
  per display for one file with 30 sources over a year (3.15M points), against 151 ms for the last 7 days and
  598 ms for 30, in the core image (the spec review's bench); the plan is then a `SEARCH` on the primary key
  bounded by `observed_at`.*
- **An interval selector, as Grafana's** (operator, 2026-10-13), replaces paging on those tables: `from` and
  `to` in the query string (UTC, the webui's time format), presets (last hour, 6 hours, 24 hours, 7 days) and a
  custom interval, whose fields are read as UTC and labelled so; the default is the last 7 days. **Previous** and
  **Next** shift the interval by its own length. A requested interval longer than 7 days is cut to the 7 days
  ending at its `to`, and the page says so. One sentence above the table says that periods are cut at the
  interval's edges; no row is marked, since telling a cut period needs a point beyond the edge, one more seek per
  identity and edge for a minor fact (operator, 2026-10-13). *Reason: a researcher looks at a moment, not at
  page 4; 7 days is the ceiling that keeps a display under half a second.* (Corrected: the interval also
  bounds the file page's search "Observations" timeline, one interval for the whole file page; the
  timeline reads `observations` per variant of the file with `observed_at` within `from` and `to`, a seek on
  the primary key, no new index. Operator, 2026-10-13.)
- **The lists stay paged**: `/sources` and the source and name pages' pair lists count files and take
  the latest point by the per-variant form of D5, never by aggregating every point of the catalog (418 ms
  against 1.0 ms at a year in the spec review's bench, and `/sources` runs it twice a request). A source's
  latest name is the name of its named variant with the latest point.
- *Reason: a period is a display of the points with a tolerance, which the reader may change without a
  migration; stored, it would need updating in place, which D1 forbids.*

### D7. `merge`

- `sources`: `INSERT OR IGNORE`, as stage 4. `source_variants`: `INSERT OR IGNORE` on `content_hash`,
  `variant_id` renumbered, as stage 4. `source_observations`: `INSERT OR IGNORE`, the variant remapped through
  `content_hash`, as `observations` is.
- No `ORDER BY`, no upsert. The stage 4 limit goes: a copy diverged from a restored catalog merges, its points
  united. `test_merger.py::test_a_copy_diverged_from_a_restored_catalog_is_refused_whole` turns into its
  opposite.
- *Reason: append-only tables merge by union, order-independent and re-runnable, the two properties `merge`
  had before stage 4.*

### D8. Migration 0011: stage 4's source tables recreated

- **0011 drops `source_ranges` and `source_variants`, with their triggers and indexes, and creates D2's
  tables**, empty, with D1's triggers. `sources` is kept as it is.
- *Reason: stage 4 is in no release and the node has never run it (it runs 4.1.0), so no catalog in use holds a
  source range. A catalog that ran the `main` image since 2026-10-12 loses its stage 4 source rows: a test
  catalog, nothing to convert. A migration rather than an edit of 0010: such a catalog is already at version
  10, and a rewritten 0010 would leave it on the old tables for good, silently.*
- The variant's `content_hash` is the writer's Python function, now over `node_id` too; no SQL function is
  registered, since 0011 computes no hash.

### D9. The documents

- The invariant, append-only for every table, in `AGENTS.md` (the Persistence row),
  `docs/contributing/architecture.md` (§1, §8.3's tables and diagram, the migration recipe's directive, §11),
  `adapters/persistence_sqlite/__init__.py:3`; `docs/operate.md:169` already says it.
- `docs/operate.md`: the source history (`:210-215`) says points, periods and D3's interval instead of every
  poll; the merge paragraph (`:127-135`) loses its limit; the expected version (`:144`) follows.
- `docs/operate.md`'s webui section: the interval selector, its presets, Previous and Next, the 7-day ceiling.
- `docs/legal.md:25` ("les plages de temps") says the reads; `merge/__main__.py:33`'s `--help` loses "source
  ranges united".
- `docs/index.md:77-81` loses the merge limit; `docs/settings.md` gains `download.sources_interval_seconds`;
  `deploy/crawler.yml` gains it, commented as its neighbours are. (Corrected: `docs/settings.md` also
  documents `webui.source_period_gap_seconds`, which `deploy/crawler.yml` gains in block 10, beside
  `webui.enabled`; `decision_poll_interval_seconds` leaves the docs, block 30.)

## 4. Measurements

### The migration's budget (spike, 2026-10-13)

A snapshot of the node's catalog taken at 10:38:40Z with SQLite's backup API inside the node's container
(version 5, 5,882,851,328 B, 12,587,498 search points), migrated in the core image `main`
(`sha256:4bee44e5...`, built from `70f4f16`, SQLite 3.46.1) under the core service's limits (`--memory 2g`,
`--pids-limit 512`, `no-new-privileges`, user 1000), on Docker Desktop.

| Phase | Wall | Anon peak | Disk on `data/` beyond the catalog | Temp in `/var/tmp` | Result |
|---|---|---|---|---|---|
| `VACUUM INTO` of version 5 (section 9's copy) | 502.5 s | 11 MB | the copy, 5,670,723,584 B | none | 5.67 GB |
| `open_catalog`, 0006 to 0010 | 674.9 s (0007 445.6, 0008 148.1, 0009 79.0) | 352 MB | WAL, +255,502,856 B | 245 MB | 222 MB, version 10 |

- No OOM kill, no `SQLITE_FULL`. Memory is not the constraint.
- Stage 1's migrations and the copy make the node's upgrade from 4.1.0 about 20 minutes long, the webui down
  meanwhile. They back section 9, not this lot's work.
- The spike also prototyped the draft's search conversion (29.1 s, then a `VACUUM` to 67 MB): not this spec's
  work, kept for the record in the spike's directory.

### Volumes

| | Rows a year | Size a year | Source |
|---|---|---|---|
| search points, 4.1.0's pace | about 45M | about 0.77 GB | the spike's version 10 pages, over 101 days |
| source points every 30 s (rejected, D3) | about 55M | about 1.3 GB | 52 source rows, 2,880 reads a day, 23.9 B a point |
| source points every 5 minutes (D3) | about 5.5M | about 0.13 GB | 52 source rows, 288 reads a day, 23.9 B a point |

The 52 rows are stage 4's probe (2026-10-11, 21 downloads); 23.9 B a point is measured by the spec review's
bench (5,466,240 points, 130,699,264 B of pages, `dbstat`, in the core image).

## 5. Alternatives rejected

- **Ranges for search observations** (the draft, `367e4df`): 214 MB of points become 59 MB of ranges, against
  a writer bound to the latest range, a ceiling that is a permanent promise (its value from 4.1.0's cadence did
  not fit stage 2's per-channel pacing), a conversion of the history, and the loss of every instant inside a
  range. Dropped by the operator (2026-10-13): "on abandonne les plages, entièrement, et on se repose sur les
  variants pour dédupliquer".
- **Ranges for sources** (stage 4): their only gain is volume, which D3's interval gives back; their trigger is
  what makes `merge` refuse a diverged copy.
- **Monotone ranges** (the draft's D1, a range whose `last_seen_at` only grows, the writer's guard in its
  statement): merge-safe, but it keeps every cost of ranges above.
- **The instants of a range in a JSON column**: an update per read rewriting a growing blob, numbers stored as
  text in SQLite's JSONB (about 17 B a timestamp, a point's size), so neither append-only nor smaller.
- **`node_id` in the point**: D2.

## 6. Blocks

Sizes are estimates from stage 4's blocks over the same files. Each block measures itself after committing.

| # | Branch | Goal | Est. lines / files |
|---|---|---|---|
| 10 | `feat/source-observations` | The switch: D2's tables and 0011 (D8), D4's writer, D5's reads, D7's `merge`, D6's periods over the last 7 days | 950 / 22 |
| 20 | `feat/webui-source-interval` | D6's interval selector, presets, Previous and Next, the 7-day cut | 380 / 9 (Corrected: about 480 with the bounded timeline) |
| 30 | `feat/sources-interval` | D3: the key, the step's cadence, the tolerance from the spacing | 260 / 9 |
| 40 | `docs/append-only-sources` | D9 | 200 / 10 |
| 50 | `docs/source-points-closing` | Closing | 80 / 4 |

**Block 10 passes both bounds**: 0011 drops `source_ranges`, which the writer, D5's reads, `merge` and every
webui source reader name, so none can switch in a block of its own without a table kept aside for the stack's
sake alone, the split the operator refused for the draft's search switch (2026-10-13).

### Contents per block

- **10**:
  - this spec, and the draft it replaces removed;
  - `migrations/catalog/0011_source_observations.sql`;
  - `domain/source.py`, `ports/source_repository.py`: `record_readings(file, readings, read_at)` returning the
    recorded readings; `earlier_points` and `has_points_before` for `earlier_ranges` and
    `has_ranges_before`; `OpenedRange` gone;
  - `adapters/persistence_sqlite/source_repository.py`: D4, D5's queries;
  - `application/run_download_cycle.py`: the alerts over the recorded readings; `application/source_alerts.py`
    renamed in its docstrings only;
  - `merge/merger.py`: D7; `merge/__main__.py`'s `--help`;
  - `composition/app.py`: the repository and the webui constructed with the poll, until block 30;
    (Corrected: the repository only; the webui gets `webui.source_period_gap_seconds`;)
  - `webui/adapters/catalog_read.py`, `webui/domain/views.py`, `webui/composition/app.py`: D6's periods over a
    fixed last 7 days, the tolerance passed in, until block 30 from `3 x poll_interval_seconds`; the period
    tables lose their `page` parameter; (Corrected: the tolerance from `webui.source_period_gap_seconds`
    for good, so block 30 does not touch it;)
  - (Corrected: `WebuiConfig.source_period_gap` and `_parse_webui` in `adapters/config/crawler_config.py`,
    `deploy/crawler.yml`, `test_crawler_config.py`;)
  - tests: `test_migration_0010.py` pinned at version 10, a `test_migration_0011.py`, `test_source_writer.py`,
    `test_source_repository.py`, `test_run_download_cycle.py`, `test_merger.py` and `merge/helpers.py`,
    `test_webui_catalog_read.py`, `test_webui_app.py`, `test_append_only.py`, `tests/catalog_rows.py`,
    `test_connection.py` (the table set, `user_version`), `tests/composition/test_app.py`, `tests/merge/test_cli.py`.
- **20**:
  - the interval's parsing and its 7-day cut (`webui/domain`), the handlers' `from` and `to`;
  - the selector, presets, Previous and Next in `file_detail.html`, `source_detail.html` and `source_name.html`,
    within the template guard (no `{% if %}`: stage 4's handoff, "Pitfalls");
  - `test_webui_app.py`, `test_webui_format.py` or a new domain test, the templates' check.
  - (Corrected: the file page's "Observations" timeline read within the interval, `sightings.py`'s timeline
    query and its caller, and its test.)
- **30**:
  - `DownloadConfig.sources_interval_seconds`, `_parse_download`, `deploy/crawler.yml`;
  - the sources step's cadence in `run_download_cycle.py`, the last run held in `DownloadDeps` or the loop;
  - the spacing (D3) handed to the repository and to the webui instead of the poll. (Corrected: to the
    repository only, the webui having its own setting since block 10.)
  - (Corrected: `decision_poll_interval_seconds`, at the root of `crawler.yml`, is parsed and required but
    read by nothing: it joins `_REMOVED_KEYS` and leaves `CrawlerConfig`, `deploy/crawler.yml` and the docs.
    Operator, 2026-10-13.)
- **40**: D9's documents.
- **50**: the closing block (`agents/workflow.md`, Wrap), which adds section 9's and the time zone's
  `BACKLOG.md` entries. (Corrected: also the `backoff` and the monotonic clock entries, and the holistic
  review's fixes.)

### Order

- 10 before 20: the selector moves the window block 10 bounds.
- 10 before 30: the interval spaces the reads that block 10 records as points.
- 40 after 30: the docs describe the result.

### Surfaces whose consumer arrives in a later block

None: block 10's tolerance reads the poll interval until block 30 hands it the spacing. (Corrected: the
writer's tolerance; the webui's is its own setting from block 10.)

### Transient states inside the stack

- Blocks 10 to 30: sources are read every poll, as stage 4 reads them, so every 30 s at the default; the
  points' volume is the rejected row of section 4's table.
- Block 10 to 20: the period tables show the last 7 days, with no way to see older ones.
- The stack merges whole, so `main` carries neither.

### Adjacent backlog items

- **"Search observations as time ranges"**: dropped by the operator (section 5); deleted at Wrap, with this
  spec's section 4 as its reason.
- **"Merge diverged copies of one node's catalog"**: closed by D7; deleted at Wrap.
- **"Paginate the file detail timeline"**: stays open; this lot leaves search observations as they are.
  (Corrected: closed by block 20, which bounds the timeline by the page's interval; deleted at Wrap.)
- **"Sort the files view by first seen"**: stays open; it touches `/files`, which this lot does not.
- **Stage 5**: stays open; its clients feed D2's tables through `SourceReading`, at D3's interval.
- **The webui in the visitor's time zone**: a new entry, agreed by the operator (2026-10-13), added at Wrap. The
  webui keeps rendering UTC and the browser converts every date with JavaScript (`Intl`, the offset of each
  date's own day); it needs `AGENTS.md`'s "Python only" amended and a JS test chain. This lot stays in UTC.
- **A copy before a migration that rewrites rows**: a new entry, agreed by the operator (2026-10-13), added at
  Wrap, linking section 9; required before the next release.
- (Corrected: **`backoff` under the search config**: a new entry, agreed by the operator (2026-10-13), added
  at Wrap. `backoff` sits at the root of `crawler.yml` but only search reads it (`BackoffRegistry`); it moves
  under the per-client search config with stage 5.)

## 7. Acceptance

Each criterion names the output that would prove it wrong. Every test is watched failing first.

- **0011** (block 10), on a seeded version 10 catalog holding stage 4 rows: `source_ranges` is gone,
  `source_variants` has `node_id`, both source tables are empty, `sources`, `files` and `match_decisions` are row
  for row unchanged, `PRAGMA foreign_key_check` is empty.
- **D1** (block 10): an `UPDATE` and a `DELETE` on `source_variants` and on `source_observations` raise
  `sqlite3.IntegrityError` (`test_append_only.py`).
- **D4** (block 10), on a real catalog: three readings of one source at three reads leave one variant and three
  points; a change of role leaves two variants; a passing state 30 s after a `queued` point records `queued`,
  one after a gap of the tolerance plus 1 µs records `undetermined`, one whose counter is below the latest
  point's records `undetermined`, one after a gap of exactly the tolerance records `queued`; a reading without
  identity or name writes nothing; the same read written twice leaves the points unchanged; a negative counter
  raises `sqlite3.IntegrityError` instead of being dropped.
- **D5** (block 10), on the application's fakes and on a real catalog: stage 4's D9 cases (its acceptance,
  "`new-source` and `reappeared`") hold over points; a source useful at three consecutive reads emits one
  `SourceNew` in total; the number of SQLite VM steps of both queries (`set_progress_handler`) is the same,
  within 10%, for a source of 1,000 points and one of 100,000; the join form of D5's reason fails it.
  (Corrected: also within 10% with 100 and with 10,000 other variants on this node, for D5's read and D4's
  carried role; the plan on the `node_id` index fails it. Holistic review.)
- **D6** (block 10): points at 0, 30, 60 s then 600 s, one variant, a tolerance of 90 s, give two periods, and
  a gap of exactly 90 s keeps one; a counter that drops between two points 30 s apart cuts a period; a `sending`
  period from counter 400 to 900 shows 500 B received; a `queued` one shows none. One identity read `queued`,
  `sending`, `queued` 30 s apart gives three periods; `sending` (counter 100), `standby` (600), `sending` (700)
  gives three, and neither `sending` period counts the 500 B of the `standby` one. Periods joined per variant
  fail both. The file, source and name pages answer 200 on a seeded catalog. On a seeded file of 3,000,000
  points over a year (30 sources, one point each every 5 minutes), in the core image under `--memory 2g`, the
  file page's period query answers in under 500 ms; the same query without the interval's bound fails it.
- **D6's selector** (block 20): `from` and `to` 3 days apart show the points of those 3 days only; Previous moves
  both 3 days back and Next 3 days forward; 30 days requested show the 7 days ending at `to` and say so; no
  parameter shows the last 7 days; a period crossing `from` starts at the first point inside the interval.
  (Corrected: a timeline over 7 days shows only those 7 days' observations; the same read without the
  bound fails it.)
- **D7** (block 10): two catalogs sharing a variant and holding different points merge, in either order, into
  the union; re-merging either changes no row; the diverged-copy fixture merges; any `MergeError` fails it.
- **D3** (block 30): with an interval of 300 s and a poll of 30 s on a fake clock, eleven rounds 30 s apart read
  sources at the first and the eleventh only; absent, the key gives 300; `0`, `-1`, `.inf` and `.nan` raise a
  `ConfigError` naming `download.sources_interval_seconds`. (Corrected: a `crawler.yml` holding
  `decision_poll_interval_seconds` raises the removed-key `ConfigError`; for every delay key of `crawler.yml`, this one and
  `webui.source_period_gap_seconds` included, a day passes and a day and a second raises a `ConfigError`
  naming the key and its bound, 30 days for `lost_after_seconds` and `reappeared_after_seconds`.)
- (Corrected: **`webui.source_period_gap_seconds`** (block 10): absent, the key gives 990; `0`, `-1`, `.inf`
  and `.nan` raise a `ConfigError` naming it; the composition hands it to the webui in every run mode.)
- **Docs** (block 40): `uv run poe docs-build` passes; `sed -n '77,81p' docs/index.md` and
  `sed -n '127,135p;210,215p' docs/operate.md` no longer state the merge limit nor a read at every poll;
  `git grep -n -i "sauf source_ranges\|but for
  \`source_ranges\`\|except \`\`source_ranges\`\`\|only grows its latest range" -- docs AGENTS.md README.md
  packages/crawler/src ':!**/migrations/**'` prints nothing (5 lines on 2026-10-13; 0010's own `RAISE`
  messages stay, a migration being immutable).

## 8. Risks and accepted limits

- **Unbounded growth**, as before: about 0.15 GB a year of source points at the node's size, growing with the
  number of downloads.
- **The webui computes periods at each display**, over at most 7 days: under 500 ms on a year's file (block 10's
  criterion). Seeing a sharer's whole history takes stepping back week by week.
- **Sources are read every 5 minutes**: a source present for less than that may be missed, and `new-source`
  and `reappeared` come up to 5 minutes later.
- **A catalog that ran the `main` image since 2026-10-12 loses its stage 4 source rows** (D8).
- **At-most-once events** and **a node stopped longer than 12 h**: stage 4's D9 limits, unchanged.
- **A merged catalog's periods are cut with the displaying node's tolerance** (D6): another node's reads at a
  longer interval show as one-point periods. (Corrected: with the displaying node's
  `webui.source_period_gap_seconds`, which its operator may raise.)
- **Intervals measured on the wall clock**: below. (Corrected: added at Wrap, operator 2026-10-13.)

### Intervals measured on the wall clock

(Corrected: added at Wrap. Block 30 fixed the first case alone, `735679d`; the operator had it removed
on 2026-10-13 for one change over every case, a `BACKLOG.md` item.)

- **In memory**, an interval or a deadline is measured with the injected wall clock: the sources step's gate
  (D3, `DownloadDeps.sources_read_at`), and the amuleapi client's ed2k and Kad start pacing and search
  deadlines (`adapters/mule_api/client.py`). A clock stepped back suspends the sources step until it passes
  the last start plus the interval again; stepped forward, it ends a wait early.
- **Persisted**, the search backoff's `retry_after` in `local.db` is a wall-clock instant: a clock stepped
  back makes the wait longer than its policy's maximum.
- **The fix, for its own lot**: a monotonic clock for what stays in memory, the wall clock kept for every
  stamp the catalog or the events carry, and a wait derived from a persisted time capped by its policy's
  maximum.
- *Accepted for this lot (operator, 2026-10-13): the cost is a wait too long or too short, never a wrong
  row.*

### Not measured before Act

- **The webui's period computation on the node's real points**, once the node runs this lot.
- **A source's points per day at 5 minutes** on the node, against the 288 assumed.
- **The variants' stability**, stage 4's open measure carried over: new `source_variants` per (file, source)
  per hour without a change of role, under 2, once the node runs this lot. A property that churns makes a variant
  per read and cuts every period.
- **The search points per day under stage 2's pace**, once the node runs `main`:
  `SELECT COUNT(*) FROM observations WHERE observed_at >= :since` over a day, against 4.1.0's 124k.

## 9. Deferred to its own lot

The operator took this out of the lot (2026-10-13). It is **required before the next release**: the node's next
upgrade, whatever it ships, runs stage 1's 0006 to 0009, which rewrite its 5.9 GB catalog. The design below,
with section 4's budget and the draft review's findings, is that lot's starting point; its own spec decides.

### A copy before a migration that rewrites rows

- **A migration that deletes or rewrites rows declares it**: a directive `-- migration: copy-before` on its
  first line, beside `-- migration: no-transaction` (`adapters/persistence_sqlite/connection.py:44`), the two
  never on one script. 0006, 0007 and 0008 carry it, and every later migration that deletes or rewrites rows.
- **When an open applies at least one pending migration that declares it, the runner first copies the
  catalog** with `VACUUM INTO`, to `catalog.db.pre-<NNNN>-<UTC timestamp>` next to the catalog, `NNNN` the first
  pending version: one copy per open, before the first pending migration, so it covers them all. A new
  catalog (`user_version` 0) is not copied.
- **The copy is written under a temporary name and renamed once whole**; an existing
  `catalog.db.pre-<NNNN>-*` for the first pending version is reused, not copied again. *Reason: the core
  restarts unless stopped (`deploy/compose.yml`); a migration that fails every time rolls back with the version
  unchanged, and a copy per restart would fill the disk, 5.7 GB each from version 5 (the draft's spec review).*
- **It refuses before copying when the free space is short**, with a `MigrationError` naming the space needed
  and the space free, read with `shutil.disk_usage` on the catalog's directory: the need is 2 x the size of
  `catalog.db` and its `-wal` together. *Reason: a copy that fills the disk half-way leaves less than before.
  The spike measured, from version 5, 1.007 x the catalog (the copy, 96.4% of it, plus 4.3% of WAL growth during
  0006 to 0010); from version 10, its prototype conversion grew the catalog and WAL by 65%. 2 x covers both,
  at the cost of 5.8 GB of headroom on the node's upgrade from 4.1.0.*
- **SQLite's temp files are not counted**: the core service sets no temp directory, so they go to the
  container's `/var/tmp`, on Docker's storage (245 MB at most in the spike). An accepted limit (section 8).
- **`merge --into` gets the copy too**, since it opens its destination with `open_catalog`.
- *Reason (operator, 2026-10-13): a required backup is a step an operator skips; an automatic one is not. The
  docs keep recommending a backup; the copy means nothing is lost unless the operator deletes it.
  `VACUUM INTO` is consistent and compact, and is taken from the runner's read-write connection (the spike met
  `disk I/O error` copying a WAL catalog opened read-only from a mode 444 file).*
- **Its acceptance**, from the draft review: a version 5 catalog leaves one `pre-0006` copy at version 5; a
  second open at the latest creates none, nor does an empty file; a failed migration then a second open leave
  one copy; one byte short of the need refuses before any write; `merge --into` a version 5 catalog copies once.
- **Its risks**: the upgrade from 4.1.0 needs about 11.8 GB free and takes about 20 minutes (section 4); SQLite's
  temp files, up to 245 MB, land on Docker's storage, which the check does not read.
- **What the draft review and this spec's review found, for that lot**: a temporary copy left by an interrupted
  `VACUUM INTO` must be removed before copying again (`VACUUM INTO` refuses a non-empty target, `file is not a
  database`); the reuse rule must cover a failure after the first pending migration committed (0006 commits,
  0007 fails: no second copy `pre-0007`), and say what the free-space check needs when a copy is reused; the
  copy is named after the catalog's file, since `merge --into` opens any name; "the two directives never on one
  script" needs its reason or goes; the 65% growth is the draft's search conversion, kept as a margin, not a
  migration this lot ships.
