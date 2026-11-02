# A file's size stored once

Tier Spec. Discussed with the operator on 2026-11-02, from `BACKLOG.md`'s "A file's size stored once", which block
10's first commit moves under "Must be done before the next release" with this spec.

## 1. In short

The node keeps a file's size in four places: `files.size_bytes`, each observation variant's `size_bytes` (part of the
variant's hash), local.db's `downloads.size_bytes`, and the values that carry it twice (`CatalogEntry` and
`FileHistory` beside their latest observation, `TierRise` beside its eD2k link). An eD2k hash names one content, so a
file has one size: the lot keeps it in `files` alone and removes the rest. It does so in v5's unreleased migrations,
so the upgrade from v4 rewrites nothing more.

On the way, the observation store stops writing with `INSERT OR IGNORE`, which silently drops a row breaking a
`NOT NULL` or a `CHECK`: such a write now fails.

## 2. What the operator will see

- The file page's timeline loses its size column; the page still gives the file's size above it (D4).
- In the SQL console, `observation_variants` and `downloads` have no `size_bytes`; a file's size is `files.size_bytes`
  (D1, D5).
- A tier rise notification is unchanged: the file's name, its size and its eD2k link (D6).
- The upgrade to v5 adds no migration and no pre-migration copy (D2).
- A catalog a pre-lot v5 build migrated past 0008 fails the crawler's first observation write instead of losing every
  observation silently (D7).

## 3. Decisions

- **D1. A file's size lives in `files.size_bytes` alone: the observation variants lose their `size_bytes`, and their
  `content_hash` hashes the seven other columns.** *An eD2k hash names one content, so a file has one size; another
  size for a known file is absurd (operator, 2026-11-02). Every network stage 5 plans names a file by an id that fixes
  its size (the table of D8 of `agents/specs/2026-10-08-multi-network-architecture.md`), and none of the node's 15.8
  million v4 observations disagrees with its file (Appendix B).* This supersedes deviation 1 of
  `agents/specs/2026-06-11-data-model-design.md`, which kept a size per observation so that a peer's wrong size stayed
  visible. The domain stays: `ReportedFile.size_bytes` is the size the network announces for the file, and reading an
  observation takes it from `files`. *Grouping the key and the size into one value would touch every site that builds
  a `FileKey`, for a guarantee no type gives: one size per hash across instances (operator, 2026-11-02).*
- **D2. The unreleased migrations create the tables without the size: catalog 0007 and 0008, local 0014. No migration
  is added.** *Catalog and local migrations 0006 to 0015 are in no release (`git ls-tree` of `v4.1.0` lists 0001 to
  0005 of each), and no catalog to keep has passed 0007 (operator, 2026-10-31), so the upgrade from v4 builds the
  tables in their final form, under the one pre-migration copy the opener takes before all pending migrations: no
  pass over the rows is added, as in D3 of the lot "One domain type for arbitrary JSON" and D1 of "Every catalog table
  STRICT".* 0007 and 0008 change together: 0008 copies each variant under its `variant_id` into a `UNIQUE`
  `content_hash`, so 0007 folds the variants that differed by size alone first. *Before the v5 tag (operator,
  2026-11-02): after it, the same change would be a new migration and a full copy of every node's catalog.*
- **D3. A file in the catalog always has a latest observation: `CatalogEntry.latest_observation` and
  `FileHistory.latest_observation` are mandatory, and both lose `size_bytes`, read from that observation.** *The
  observation store writes a file in the transaction of its first observation, and is the only writer of `files` with
  0008 (whose v4 writer did the same) and `merge`; the node's catalog holds no file without an observation
  (Appendix B). The `None` was an impossible state, and the size the same fact twice in one value (operator,
  2026-11-02).* The size sort stays on `files.size_bytes`. The source pages follow the same rule: their
  `best_filename_by_file` holds every file of their sharing periods, and the webui's short-hash fallback for a file
  goes. *A source variant needs a `files` row, written with its first observation, so only tests reached that fallback
  (operator, 2026-11-02).* A file without an observation, which only a forged merge source can bring, is left out of
  the files list, the file page and the source pages (section 7). `FileJudge.rejudge` raises a `RuntimeError` naming
  the file when it finds no best observation, in place of its fallback (the candidate's filename and a size of 0).
  *It runs only right after an observation is recorded or over observed files, so the case is a bug, which in-process
  code lets crash loudly (`AGENTS.md`, boundary discipline); its two callers absorb `StoreError` alone (operator,
  2026-11-02: "an abnormal case").*
- **D4. The file page's timeline loses its size column.** *Every line would show the file's size, which the page
  states above the timeline (operator, 2026-11-02).*
- **D5. local.db's `downloads.size_bytes` is dropped, with the `size_bytes` of `TrackedDownloadWriter.record_queued`.**
  *Written at queue time, it is read by no code: `SqliteNodeStateReader` names its columns without it, and the disk
  floor's admission measures what the client's queue still has to transfer (`DownloadStatus`) and takes the
  candidate's size from the catalog (section 1 of `agents/specs/2026-09-13-real-disk-cap-and-lost-download-ttl.md`)
  (operator, 2026-11-02).* This supersedes that section's "leave the column (it is harmless catalog data and dropping
  it buys nothing)": 0014 rebuilds `downloads` before any release, so the drop costs no pass.
- **D6. `TierRise` carries the file (`FileKey`), its filename and its size, and the apprise notifier builds the eD2k
  link.** *The link holds the name, the size and the hash, so the value said each twice; the notifier already writes
  the rest of the message, as `AGENTS.md`'s "the domain writes plain text" wants (operator, 2026-11-02).*
- **D7. Every `INSERT OR IGNORE` of the crawler becomes `INSERT ... ON CONFLICT (<key>) DO NOTHING`: the observation
  store's three and migration 0007's two.** *`INSERT OR IGNORE` drops a row breaking a `NOT NULL` or a `CHECK` without
  an error, where `ON CONFLICT ... DO NOTHING` ignores the duplicate alone and raises on the rest (Appendix C). Under
  D1, a catalog a pre-lot build took past 0008 would otherwise lose every new observation silently: its variants still
  require a size, and the store would commit the `files` row alone (`size-once-survey`). The class is fixed, not the
  case (operator, 2026-11-02).* `require_canonical_native_id` stays: the decision store uses it too, and its error
  names the hash. The gate keeps the class out: sqlfluff's built-in `CV09` (`convention.blocked_words`, `blocked_words
  = ignore`) refuses the keyword in the SQL files, and a `code-pattern-check` rule refuses `OR IGNORE`, any case, in
  every Python string. *The operator's order puts a gate tool before a convention, and sqlfluff and ast-grep already
  run in the gate; neither reads the other's files (operator, 2026-11-02, choosing `CV09` over a test of our own).*
  `CV09` also refuses `ON CONFLICT IGNORE` in a constraint and `RAISE(IGNORE)` in a trigger, the same silent skip; no
  migration holds either (Appendix C).

The operator decided D1 to D7 on 2026-11-02.

## 4. Acceptance

Each criterion fails on `main` but the last two, which state what must not change.

**The catalog (D1, D2, D7)**

| # | Check | After the lot | On `main` |
|---|---|---|---|
| 1 | `observation_variants`'s columns, on a catalog the opener creates (`pragma_table_info`) | no `size_bytes` | `size_bytes` |
| 2 | The SQL function `content_hash` | seven arguments | eight |
| 3 | A v4 catalog migrated: a file of size 100 observed twice under one name, once reported at 100, once at 101 | one variant; both observations read back 100 (Corrected: through the timeline's `observations_between`, the reader port giving only the latest and the best) | two variants; one reads back 101 |
| 4 | `record_observation` twice for one file, the two reports differing by size alone | one variant; both read back the first size (Corrected: as in 3) | two variants |
| 5 | `record_observation` on a catalog whose variants carry an extra `NOT NULL` column the store does not write | raises `NOT NULL constraint failed`, writes no row | returns, commits the `files` row alone |
| 6 | `uv run poe sql-lint` and `uv run poe code-pattern-check`, with block 10's checks | pass | fail, naming 0007's two inserts, the store's three and its docstring |
| 7 | The new ast-grep rule's tests | refuse `INSERT OR IGNORE`, `insert or ignore` and `OR IGNORE` alone on a line; accept `ON CONFLICT DO NOTHING` | no rule |

**The reads and the webui (D3, D4)**

| # | Check | After the lot | On `main` |
|---|---|---|---|
| 8 | `CatalogEntry` and `FileHistory` (mypy) | no `size_bytes`; `latest_observation: FileObservation` | `size_bytes`; `FileObservation \| None` |
| 9 | A `files` row without an observation | absent from the files list; `read_file_history` gives `None`; its periods absent from both source histories | listed; a history without observation; periods under the short hash |
| 10 | `_file_sharing_period_display`'s `best_filename` (mypy) | `str` | `str \| None` |
| 11 | `rejudge` when the reader gives no best observation | raises `RuntimeError` naming the file, dispatches nothing | dispatches a `DecisionsRecorded` of size 0 |
| 12 | The file page | the `Size` `<dd>` holds the size; timeline rows of four `<td>`, none holding it | five `<td>`, one holding the size |

**local.db and the notification (D5, D6)**

| # | Check | After the lot | On `main` |
|---|---|---|---|
| 13 | `downloads`'s columns, on a local.db the opener creates and on a v4 local.db migrated (its downloads kept) | no `size_bytes` | `size_bytes` |
| 14 | `record_queued` (mypy) | no `size_bytes` | `size_bytes` |
| 15 | `TierRise`, and the apprise notifier's body | no `ed2k_link`; the body's link built by the notifier from the rise's file, filename and size | `ed2k_link`, built by the policy |

**What must not change**

| # | Check | Expected |
|---|---|---|
| 16 | `ls` of `migrations/catalog` and `migrations/local`, and `grep -l "copy-before"` over them, at the stack's top | the same fifteen files each and the same marked files as on `main` |
| 17 | `uv run poe check` at each block's tip; CI's `validate / gate`, the compose smoke included (it seeds a download row) | green |

## 5. Blocks

Estimates by `size-once-estimates` (Sonnet), 2026-11-02, report `.reviews/size-once-estimates.md`: blocks 10, 20, 30
and 40 together, 50 and 60 together, 70 and 80 implemented in a throwaway copy of `ac1c5aae` and measured with the
command of `agents/workflow.md`; the cuts estimated. The bound is checked after committing.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `fix/insert-on-conflict` | D7 | about 110, 10 |
| 20 | `refactor/variant-without-size` | D1, D2 for the catalog | 170 (140 to 230), 16 |
| 30 | `refactor/file-size-from-latest-observation` | D3 for the files list, the file page and the judge, D4 | about 190, 17 |
| 40 | `refactor/source-pages-best-filename` | D3 for the source pages | about 85, 8 |
| 50 | `refactor/queued-download-without-size` | D5 | about 85, 13 |
| 60 | `refactor/downloads-table-without-size` | D2 for local.db | about 20, 4 |
| 70 | `refactor/tier-rise-link-in-notifier` | D6 | 50 (40 to 75), 6 |
| 80 | `docs/wrap-file-size-stored-once` | closing, section 6's documents | 25 (15 to 40), 3 |

Block 10 comes first so that block 20 edits store statements already in their final form; it turns 0007's two inserts
too, since its `CV09` would otherwise fail the gate on them. Its row is the lead's estimate: the measured store change
(45 lines, 2 files) plus the checks, D7's second half, decided after the measure. Block 30 follows block 20,
whose observations read their size from `files`. Blocks 30 and 40, and 50 and 60, are one change each cut in two:
whole, they came to 18 and 17 files, up to 19, against the bound of 20. Block 30 is green alone because the source
pages keep their fallback until block 40; block 50's store omits the column, whose `DEFAULT 0` fills it until block 60
drops it.

## 6. Documents

- `docs/migration-4x.md`, the SQL console's schema: a file's size in `files.size_bytes` only, `downloads.size_bytes`
  gone (block 80). The console's schema is documented nowhere else.
- `docs/contributing/architecture.md`: the inserts idempotent by `ON CONFLICT DO NOTHING` alone (`:476-477`), a variant
  without the size (catalog 0007, `:492-494`), and no more `INSERT OR IGNORE` as the reason the domain validates first
  (`:603-604`) (block 80). (Corrected: at the stack's top the lines were 477-478, 492-494 and 604; block 80 located
  them by content.)
- `AGENTS.md`, Hard rules: inserts by `ON CONFLICT ... DO NOTHING`, never `OR IGNORE` (block 10).
- `AGENTS.md`, the glossary's `catalog entry`: "its latest observation, its current decisions", the size dropped
  (block 30).
- The closing block's handoff.

## 7. Limits and scope

### Accepted limits

- **A peer announcing a hash with another size than its content's gives that size to the file if it is the first
  recorded: same hash, same file** (D1). A later announcement changes nothing, `files` keeping its first write; the
  file page's eD2k link, the download request and the disk admission read `files.size_bytes`, where `main` read the
  latest or best report's. The node's data holds no such announcement (Appendix B) (operator, 2026-11-02).
- **A forged merge source can bring a `files` row without an observation**, which `merge` copies as on `main`: the files
  list, the file page and the source pages leave it out, while the counts above the files list, its tier facet, the
  target coverage and the file counts of the sources list and of a source's names still count it. A merge is between
  peers one trusts, as the lot "Every catalog table STRICT" accepted for an orphan observation (operator, 2026-11-01).
- **A catalog a pre-lot v5 build migrated keeps its tables**: past 0008, the crawler's first observation write fails
  (D7) and `merge --into` it fails on its variants' size; at exactly 7, 0008 fails on two variants differing by size
  alone. No catalog to keep has passed 0007 (operator). A local.db past 0014 keeps `downloads.size_bytes` with its
  `DEFAULT 0`, so the store's insert without it still works.

### Backlog

Block 10's first commit moves "A file's size stored once" under "Must be done before the next release", as agreed on
2026-11-02. The closing block deletes it. No entry is added.

### Adjacent backlog items

- "`merge` refuses a source whose schema is not the node's": a pre-lot catalog as a source is already refused after
  the lot, since the copier recomputes each variant's `content_hash` on seven columns and refuses a stored eight-column
  one; the entry covers every other schema difference, so it stays open.
- "Multi network", stage 5: its networks name files by ids that fix their size, D1's premise, and this lot needs no
  stage 5 work; it stays open.
- "Sort the files view by first seen": the sort allowlist this lot leaves as it is; it stays open.
- "aMule 3.2.0 pinned", "The Grype scan back on p2pwatch": with this lot, the conditions of the v5 tag; they stay open.
- "Test quality", "Mutation testing in the gate", "Contract tests for the fakes of outside systems", "A generic way to
  write the tests' stubs and spies", "The webui in the visitor's time zone", "Adopt ty", "A rule test naming no rule
  fails the gate": unrelated; they stay open.

## Appendix A. Design, block by block

Paths: `c:` is `packages/crawler/src/p2pwatch/`, `p:` its persistence adapter `c:adapters/driven/persistence_sqlite/`,
`t:` is `packages/crawler/tests/`.

### Block 10: `ON CONFLICT` everywhere (D7)

- `p:sqlite_observation_store.py`: each insert ends in `ON CONFLICT (<key>) DO NOTHING`, the key being `file_id` for
  `files`, `content_hash` for the variant and the primary key for the observation. An `INSERT ... SELECT` needs
  `WHERE true` before its `ON CONFLICT`, as the copier writes it.
- The store's docstring drops the reason `INSERT OR IGNORE` gave the hash guard; the guard stays.
- Migration 0007: its two inserts the same way.
- The checks:
  - `packages/crawler/pyproject.toml`: `[tool.sqlfluff.rules.convention.blocked_words]`, `blocked_words = "ignore"`.
  - `ast-grep/rules/`: a rule over Python strings, `(?i)\bOR\s+IGNORE\b`, its tests in `ast-grep/tests/`; the root
    `pyproject.toml`'s `code-pattern-check` help names it.
- Tests: acceptance 5 (the variants gain a `NOT NULL` column by a table rebuild, then a write). The test strings holding
  `OR IGNORE` move to `ON CONFLICT`: `t:support/catalog_rows.py`, `test_sqlite_catalog_copier.py`,
  `test_sqlite_observation_store.py`. (Corrected: in `test_sqlite_catalog_copier.py` it was a comment and a test name,
  `test_t2_merge_overlapping_identity_files_or_ignore`, now `..._keeps_one`.)
- `AGENTS.md`, Hard rules: an insert ignores a duplicate by `ON CONFLICT (<key>) DO NOTHING`, never by `OR IGNORE`.
  (Corrected: written `ON CONFLICT ... DO NOTHING`, as section 6 has it, since the merge copier's six inserts are
  keyless; the store and 0007 name their keys.)

### Block 20: the variants without the size (D1, D2)

- Migration 0007: `size_bytes` leaves the variants' table, the `SELECT DISTINCT` key and both `content_hash` calls,
  so the variants that differed by size alone fold into one.
- Migration 0008: the variants' table without `size_bytes` and its `CHECK`, its copy and its rehash without it.
  `files` is unchanged.
- `p:variants.py`: `content_hash` on seven columns, in Python and in its SQL registration; the copier's
  `_check_catalogs`, `_VARIANT_COLUMNS` and `_OBSERVATION_VARIANT_HASH` the same.
- `p:observation_read.py`: the size read from `f.size_bytes`; both queries already join `files`.
- The store's docstring drops deviation 1.
- Tests: `test_sqlite_database_opener.py` (acceptance 3), `test_sqlite_observation_store.py` (acceptance 4;
  `test_record_observation_twice_first_seen_wins_in_files` drops its "anomaly stays visible"), `test_variants.py`,
  `test_append_only.py`, `test_migration_0007.py`, `test_migration_0008.py`, `test_sqlite_catalog_file_reader.py`.
- Support: `t:support/catalog_rows.py`, `t:support/adapters/driven/persistence_sqlite/helpers.py` and
  `older_catalog.py`.

### Block 30: the files list, the file page and the judge (D3, D4)

- Domain: `CatalogEntry` and `FileHistory` drop `size_bytes`; their `latest_observation` is mandatory.
- `p:observation_read.py`, `LATEST_OBSERVATION_CTE`: its two `LEFT JOIN`s become `JOIN`s and its two
  `filename IS NOT NULL` go, since the CTE itself gave a row of `NULL`s for a file without an observation.
- `p:sqlite_catalog_file_reader.py`: the list joins the latest observation, `file_size_bytes` goes;
  `read_file_history` returns `None` for a file without an observation, as its port's docstring now says.
- `c:application/use_cases/describe_file.py` and the webui (`app.py`, `displays.py`, `templates/file_history.html`):
  the `None` branches go, the size comes from the latest observation, `ObservationDisplay.size_bytes` and its column
  go (`colspan` 4).
- `c:application/steps/file_judge.py`: raises in place of its fallback.
- Tests: the never-observed tests of `test_sqlite_catalog_file_reader.py`, `test_app.py` and `test_describe_file.py`
  go with the state, `_seed_file_without_observation` staying for acceptance 9 (Corrected:
  `test_read_matched_and_total_file_counts_counts_file_with_no_observation` stays, pinning section 7's second limit); `catalog_file_reader_contract.py`
  reads the size from the latest observation; `test_file_judge.py`'s
  `test_a_file_with_no_name_left_is_named_by_the_candidate` becomes the raise's test (acceptance 11).
- `AGENTS.md`, the glossary's `catalog entry`: the size dropped.

### Block 40: the source pages (D3)

- `p:sqlite_source_reader.py`: `_best_filename_by_file`; both histories leave out the periods on a file it does not
  hold.
- `c:application/ports/driven/source_reader.py`: the two histories' docstrings say every period's file has its best
  filename. (Corrected: unchanged, a docstring holding two lines at most; the promise sits in the
  `best_filename_by_file` field comments of `SourceHistory` and `SourceNameHistory`, fix-back `4e0fdd31`.)
- `c:domain/source_history.py`: its two field comments.
- Webui: `app.py`'s `_file_sharing_period_display` loses its `short_hash` fallback, while `_sharing_period_display`
  keeps its "unknown" for a source without a user hash; `displays.py`'s comments on a file never seen.
- Tests: `source_reader_contract.py` states only that every period's file has its best filename, since no Writer can
  produce the absence (Corrected: unchanged, its two history tests already comparing the whole
  `best_filename_by_file`); the adapter's `test_a_page_s_file_never_observed_has_no_best_filename` becomes the absence test.

### Block 50: `record_queued` without the size (D5)

- `c:application/ports/driven/tracked_download_writer.py`: `record_queued` drops `size_bytes`.
- `p:sqlite_tracked_download_store.py`: the insert omits the column, which its `DEFAULT 0` fills until block 60.
- `c:application/steps/download_decider.py`: keeps the size for its disk admission and stops passing it.
- The fake store drops `sizes`, read by nothing and written by hand in `test_download_cycle.py` and
  `test_download_starter.py`; every `record_queued` call follows.

### Block 60: the `downloads` table without the size (D2)

- Local migration 0014: `downloads` created and copied without `size_bytes`. Local 0007 is untouched: it carries the
  column, 0014 drops it.
- Tests: `test_migration_0002.py`'s `test_downloads_has_size_bytes_column`, which opens a fully migrated local.db,
  becomes 0014's test of the column's absence; `t:integration/test_compose_smoke.py`'s `_SEED_ROW` drops the column
  (CI only).

### Block 70: the link built by the notifier (D6)

- `c:domain/observability/notification.py`: `TierRise` gains `file: FileKey` and drops `ed2k_link`.
- `c:domain/observability/policy.py` → `c:adapters/driven/observability/apprise_notifier.py`: the `match` on the
  network and `build_ed2k_link` move into `_rise_body`.
- No `tach.toml` change: `tach check` does not see an import across distributions, and `amule_api_client.py` already
  imports `build_ed2k_link` from an adapter.

## Appendix B. Facts, 2026-11-02

**The operator's catalog** (`/home/geoffrey/Projets/mulewatch/data/catalog.db`), the node stopped, read `mode=ro`;
re-run by `size-once-spec-review` with the same figures:

| Fact | Figure |
|---|---|
| `user_version`, catalog and local.db | 5 |
| Files | 2 162 |
| `file_observations` | 15 763 676, from 2026-07-04 to 2026-10-28 |
| Observations whose size differs from their file's | 0 |
| Files without an observation | 0 |

The last two, in order:

```sql
SELECT COUNT(*) FROM file_observations o JOIN files f ON f.ed2k_hash = o.ed2k_hash
WHERE o.size_bytes <> f.size_bytes;
SELECT COUNT(*) FROM files f
WHERE NOT EXISTS (SELECT 1 FROM file_observations o WHERE o.ed2k_hash = f.ed2k_hash);
```

**The tree:**

- `git ls-tree` of `v4.1.0`, the newest tag: catalog and local migrations 0001 to 0005 only.
- `SqliteDatabaseOpener.open` takes one pre-migration copy before all pending migrations (`ensure_copy` over
  `pending`).

**`size-once-survey`** (`.reviews/size-once-survey.md`, base `ac1c5aae`):

- no migration from 0009 to 0015 names `observation_variants.size_bytes`;
- `content_hash` has five callers: the store, the copier, 0007 (twice) and 0008;
- no production code reads `downloads.size_bytes`;
- `node_id` is in a variant's hash, so `merge` never folds two nodes' variants.

**`size-once-spec-review`** (`.reviews/size-once-spec.md`):

- with the lot's inner joins, every observation and variant is still reached by a key or an index seek
  (`EXPLAIN QUERY PLAN` on a current-schema catalog);
- `ON CONFLICT (file_id)` on `files` returns quietly on a duplicate that also breaks `UNIQUE (network, native_id)`.

## Appendix C. Probes, 2026-11-02

**SQLite** 3.54.0 (the host's) and 3.49.1 (the venv's, the image's line), re-run by `size-once-spec-review`: a
`STRICT` table with a `NOT NULL` column, a `CHECK` and a `UNIQUE` key, holding one row.

| Insert | `NOT NULL` column left out | `CHECK` broken | Key repeated |
|---|---|---|---|
| `INSERT OR IGNORE` | returns, `rowcount` 0 | returns, `rowcount` 0 | returns, `rowcount` 0 |
| `ON CONFLICT (<key>) DO NOTHING` | `IntegrityError: NOT NULL constraint failed` | `IntegrityError: CHECK constraint failed` | returns, `rowcount` 0 |
| `ON CONFLICT DO NOTHING` | `IntegrityError: NOT NULL constraint failed` | `IntegrityError: CHECK constraint failed` | returns, `rowcount` 0 |

The table still holds its one row after each.

**sqlfluff** 4.3.0, `CV09` with `blocked_words = ignore`, sqlite dialect:

| Input | Result |
|---|---|
| `INSERT OR IGNORE ...` | fails, `Use of blocked word 'IGNORE'` |
| `insert or ignore ...` | fails, `Use of blocked word 'ignore'` |
| `INSERT ... ON CONFLICT DO NOTHING` | passes |
| The crawler's migrations | fail on 0007's lines 37 and 67, nothing else |
