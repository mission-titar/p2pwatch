# Values checked at the boundary

Tier Spec. Discussed with the operator on 2026-10-30. Found while discussing the round-trip contracts. Ships before the
v5 tag (D7).

## 1. In short

The node supports UTF-8 text only, but nothing enforces it, nor the range of the integers it stores. Today only the
operator's config breaks the rule: a keyword that is not valid UTF-8 stops the crawler at its first search, and a unit
separator in a target letter or a rule name breaks the files page. amuled already sends valid values; the next mapper
(stage 5), or a change of amuleapi's format, may not, and the store would then stop the process.

The lot gives every boundary one rule: the domain refuses a value it cannot carry, the mapper cleans what a network
sends, and the config refuses what the operator wrote. *(Added after the holistic review: `merge` refuses what another
catalog holds, D9.)*

## 2. What the operator will see

- `validate-config` and `crawl` refuse a config file holding text that is not valid UTF-8, a control character in a
  target letter or a rule name, or an environment variable that is not valid UTF-8; each error says where.
- `merge` checks every source before touching the destination, and refuses one holding a value the node could not
  read back, saying where; it copies each source whole or not at all, and no longer drops a row in silence. *(Added
  after the holistic review, D9.)*
- Nothing else changes: amuled's answers already pass every new check, and so does the operator's catalog.

## 3. Decisions

- **D1. The mapper replaces invalid UTF-8 in every text a network sends with `�`, and keeps the value.** *UTF-8 is
  the only text the node supports, and dropping the result could lose an episode for one damaged character.*
  Block 10.
- **D2. The mapper reads an integer below 0 or above what the catalog holds as malformed, as it already reads a
  malformed one: a count as 0, a duration or a bitrate as absent, a size by dropping the result.** *No count, size,
  duration or bitrate is negative; a size read as 0 would catalogue a file aMule refuses to download.* Block 10.
- **D3. The domain values that carry network data refuse invalid UTF-8 and an out-of-range integer when they are
  built.** *A future mapper that forgets D1 or D2 then fails in its own tests instead of deep in a store; a domain
  value guarantees its own rules (Evans, Domain-Driven Design).* Block 20.
- **D4. The config refuses text that is not valid UTF-8, anywhere in its files or in an environment variable it
  reads.** *Such a keyword stops the crawler; the loader already refuses a file that is not UTF-8, and this is the same
  defect written as an escape.* Block 30.
- **D5. The config refuses a control character in a target letter or a rule name.** *Both become identifiers that the
  files page splits on a control character, and no control character belongs in an identifier.* Block 30.
- **D6. Two store tests that build a value D3 refuses leave their stores' tests.** *One never tested what it claims;
  the other tests a guarantee of the schema, which belongs with the schema's tests.* Block 20.
- **D7. No v4 backport, v5 no longer waits for a second network, and the v4 node stays stopped until v5.** *Nothing
  this lot fixes is reachable from the network; aMule 3.2.0 fixes 15 advisories present in 3.1.0, several of them
  triggered by any peer, and the two-container layout and the v5 refactorings make a release on their own.* Revokes
  stage 1's D16; block 40 records it.
- **D8. No catalog migration.** *No stored row breaks D3: amuled never sent such a value and the operator's catalog
  holds none, which the lead checks again before the node upgrades.*

- **D9. `merge` checks every source before touching the destination and refuses one the node could not use, then
  copies each source whole or not at all, and no longer drops a row in silence.** *A merged row can never be deleted:
  one the node cannot read breaks the files page, the reevaluation and the download loop, and one whose ids do not
  match its keys blocks the node's own writes. Types, signs and closed sets are left to the STRICT lot, due before v5,
  so these blocks write no check the schema will soon hold.* Blocks 35 and 37.
- **D11. A source the destination's schema refuses during the copy leaves the earlier sources merged.** *A single
  transaction over the whole merge cannot hold more than 10 sources (SQLite neither detaches a source read in a
  transaction nor attaches more than 10), and a copy of the destination costs its size; re-running is safe, since a
  duplicate is skipped.* Block 37.
- **D10. A merged catalog's `download` decisions keep driving the download loop.** *A merge is rare and intentional,
  between peers one trusts, and a file the webui shows as a download should be in the client too.*

The operator decided D1 to D8 on 2026-10-30, and D9 to D11 on 2026-10-31 after the holistic review found `merge`
unchecked; the names D3 introduces are in Appendix A.

## 4. Acceptance

1. The mapper cleans each kind of invalid text and integer of D1 and D2, which `main` lets through (Appendix B).
2. Each domain value of D3 refuses each invalid text and integer, and accepts the limits and valid non-ASCII text.
3. `validate-config` refuses each invalid config of D4 and D5 and says where, where `main` accepts it.
4. `merge` refuses a source holding each invalid value of D9 and leaves the destination as it was, in both its modes,
   where `main` merges it with exit 0.
5. `uv run poe check` passes at each block's tip.

## 5. Blocks

Estimates by `boundary-values-estimates` (Sonnet): rows 10 to 30 on 2026-10-30, rows 35 and 37 on 2026-10-31;
rows 38 to 40 by `block-40-closing`, which split the closing block past the 20-file bound (2026-10-31). The bound is
checked after committing.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `fix/amuleapi-values-cleaned` | D1, D2 | 175, 4 |
| 20 | `feat/domain-value-bounds` | D3, D6 | 285, 15 |
| 30 | `fix/config-refuses-invalid-text` | D4, D5 | 140, 8 |
| 35 | `fix/merge-refuses-invalid-sources` | D9's unreadable values, D10 | 330, 11 |
| 37 | `fix/merge-refuses-inconsistent-rows` | D9's inconsistent rows | 195, 9 |
| 38 | `fix/values-at-the-boundary-review` | first holistic review's findings | 200, 16 |
| 39 | `fix/merge-review` | second holistic review's findings | 325, 13 |
| 40 | `docs/wrap-values-at-the-boundary` | closing | 30, 2 |

The mapper comes first, so nothing arriving is refused once the domain starts refusing; block 30 reuses the domain's
check.

## 6. Documents

- `AGENTS.md`: the invariant "UTF-8 text only", and what amuleapi really sends (block 40).
- `docs/migration-4x.md`: the config values now refused (block 30).
- `docs/operate.md`, the catalog merge: what it refuses (blocks 35 and 37) and what a refusal during the copy leaves
  (block 37).
- Stage 1's D16 and the umbrella spec: a correction beside each line D7 revokes (block 40).

## 7. Limits and scope

### Accepted limits

- **A text D1 cleans is no longer the sender's**: two names differing only by invalid UTF-8 read the same.
- **A value D1 or D2 cleans leaves no trace**, except a dropped size, which a metric counts.
- **The integers inside a file's raw metadata stay unchecked**: they are stored as text and read by no decision.
- **Until the STRICT lot, `merge` copies a value of the wrong type, a negative integer (but a source's received
  bytes, which a `CHECK` already holds), an unknown tier or an instant out of range** (D9). No release separates the
  two lots, and the STRICT lot must close it.

### Backlog

With block 10's first commit, as agreed on 2026-10-30: "aMule 3.2.0 pinned" added and "Round-trip contracts" moved,
both under "Must be done before the next release" (Appendix A, D7). With block 40, as agreed on 2026-10-31: "Every
catalog table STRICT" moved there too and extended to what D9 leaves it (Appendix A, D9).

### Adjacent backlog items

- "Round-trip contracts": the next lot, whose draws D3 defines (Appendix D); it stays open.
- "Multi network", stage 5: its mappers inherit D3's guard; it stays open.
- "Every catalog table STRICT": moved before the v5 tag by the closing block, so operators pay one rebuild with v5's
  migrations, and extended to what D9 leaves it (Appendix A, D9); it stays open.
- "Contract tests for the fakes of outside systems": the fake against amuled, not what amuled sends; it stays open.
- "aMule 3.2.0 pinned", "The Grype scan back on p2pwatch": with the round-trip contracts, the other conditions of the
  v5 tag; they stay open.
- "Test quality", "Mutation testing in the gate", "A generic way to write the tests' stubs and spies", "Adopt ty",
  "A rule test naming no rule fails the gate", "Sort the files view by first seen", "The webui in the visitor's time
  zone": unrelated; they stay open.

## Appendix A. Design, per decision

For the teammates. Paths under `packages/crawler/src/p2pwatch/` unless stated.

- **D1.** In `adapters/driven/amule_api/mapping.py`, every text the mapper reads (a filename, a source name, the
  software, aMule's version, `raw_metadata`'s keys, texts and the texts of its tuples) has each surrogate, paired or
  not, replaced with U+FFFD. `json.loads` already joins the escaped pair JSON writes for a character beyond U+FFFF, so
  a surrogate left comes from bytes that are not UTF-8.
- **D2.** "What the catalog holds" is SQLite's `INTEGER`, at most 2\*\*63 - 1. The readers keep their conventions:
  `_int_or_zero` (0), `_optional_int` (`None`), the inline check of a search result's `size_bytes` (result dropped).
  amuled itself drops a result of size 0 and refuses a link of size 0 (Appendix C).
- **D3.** `p2pwatch/domain/value_bounds.py` holds `require_well_formed_text(text, *, error_label)` and
  `require_quantity(quantity, *, error_label)`, both raising `ValueError` (names: operator). A well-formed text is
  valid UTF-8: it holds no surrogate, paired or not, since a pair left in a `str` fails every sink a lone one does. A
  quantity is an integer in [0, 2\*\*63). `ReportedFile`, `SourceReading`, `DownloadStatus` and `ClientStatus` call
  them from `__post_init__` on each text field (`raw_metadata`'s keys, texts and tuple elements included) and each
  integer field, a `None` passing. `raw_metadata`'s integers stay unchecked (stored as JSON text). `FileKey` stays out:
  its `native_id` is held to its network's canonical form, a stricter rule, by `_hash_hex` and
  `require_canonical_native_id`, and stage 5 defines that form per network. `SourceKey` and `ContactPoint` are the
  precedents. `quantity` and `well-formed text` stay out of `AGENTS.md`'s glossary: each function's docstring
  defines its word.
- **D4.** `adapters/driven/config/yaml_loader.py`'s `load_yaml` walks the loaded tree once and raises a
  `BrokenInputError` naming the file and the key path, as it does for a file that is not UTF-8; its module docstring,
  which says it validates no substance, changes. `adapters/driven/config/interpolation.py`'s `interpolate_document`
  refuses a variable's value with the `InvalidConfigError` it raises for an unset one, naming the variable, since
  interpolation runs after `load_yaml`. Both through `require_well_formed_text`.
- **D5.** `packages/matching/src/catalog_matching/domain/validation.py` refuses a character of Unicode category `Cc`
  (C0, DEL, C1) in a target letter and a rule name, through `unicodedata`, since `catalog_matching` cannot import
  `p2pwatch`. The files page joins and splits `target_id` and `rule_name` on U+001F (`_split_concat`,
  `sqlite_catalog_file_reader.py`).
- **D6.** `test_rollback_on_non_sqlite_error_keeps_connection_usable` (`test_sqlite_observation_store.py`) is
  deleted, and `sqlite_observation_store.py`'s docstring loses its surrogate example: its surrogate fails in the
  content hash before `BEGIN`, and `test_record_observation_is_one_transaction` covers the rollback.
  `test_a_negative_counter_is_refused_not_dropped` (`test_sqlite_source_point_store_writer.py`) moves to
  `test_append_only.py`, seeded by `tests/support/catalog_rows.py`; that module's docstring and its
  `tests_without_unit` entry (`packages/crawler/pyproject.toml`) become "the catalog's guarantees enforced in SQL".
- **D7.** Block 40 sets a `(Corrected: ...)` beside D16 of `agents/specs/2026-10-09-stage1-generic-identity.md`, the
  "Release" line and the stage 3 row of `agents/specs/2026-10-08-multi-network-architecture.md`, and the restatement
  of 2026-10-27 in `agents/handoffs/2026-10-30 - handoff - keyword-only calls.md`. The advisories any peer triggers:
  GHSA-52mv (Kad), GHSA-cvxg (eD2k), GHSA-hv8p and GHSA-7rxg (a source). The backlog entry added with block 10:
  "**aMule 3.2.0 pinned**: `ARG AMULE_VERSION` and `ARG AMULE_COMMIT` moved from 3.1.0 to 3.2.0, which fixes 15
  advisories, by the weekly bump or by hand. `packages/amule/Dockerfile`, `.github/workflows/amule-bump.yml`."; the
  "Round-trip contracts" entry's link extends to Appendix D.
- **D8.** The operator first chose a migration rewriting negative values, on a premise the second spec review
  disproved (amuled drops sizes out of range). The lead re-runs Appendix C's two queries on the operator's catalog
  before the node upgrades to v5.
- **D9.** `adapters/driven/persistence_sqlite/sqlite_catalog_copier.py` runs two passes, attaching one source at a time
  since SQLite attaches at most 10 databases (`SQLITE_MAX_ATTACHED`). The check pass runs on a connection to `:memory:`
  carrying the check functions, before `open_catalog` creates (`--output`) or migrates (`--into`) the destination, so a
  refused check writes nothing at all. The copy pass then copies each source in its own transaction (D11). A check's
  refusal raises `CatalogCopyError` naming the source, the table, the column and the first offending row's key, and
  reaches the operator as `Merge failed: ...`, exit 2. Block 35 holds the two passes, the checks of unreadable values
  and that error; block 37 the consistency checks and D11. The checks run in SQL over the attached source, through
  registered functions, in this order, since a Python function handed a text that is not UTF-8 raises SQLite's generic
  `user-defined function raised exception` before its body runs:
  - every TEXT column of every table is valid UTF-8, first: a function over `CAST(x AS BLOB)` decoding strictly, which
    refuses what `require_well_formed_text` refuses (SQLite has no UTF-8 validator, and fetching invalid bytes raises an
    `OperationalError` that names no row);
  - every `raw_metadata` (a JSON array of pairs in `observation_variants`, a JSON object in `source_variants`) is JSON
    of that shape whose every text passes `require_well_formed_text`: an escaped surrogate is valid UTF-8 until a read
    decodes it;
  - `match_decisions.target_id` and `rule_name` hold no `Cc` character, through D5's rule, shared as
    `has_control_character(text) -> bool`, public in `catalog_matching/domain/validation.py` (name: operator,
    2026-10-31), which its validation and the copier both call;
  - block 37: `files.file_id` and `sources.source_id` equal the ids their `network` and `native_id` derive, on the rows
    whose `network` the node knows (the schema's `CHECK` refuses the others at copy time, and `file_id` raises on an
    unknown one), and each variant's `content_hash` equals the hash of its values, the observation variants' through the
    registered `content_hash`, the source variants' through their store's hash, moved into `variants.py` and registered
    the same way. A non-derived `file_id` would make the node's own `record_observation` of that key fail for good.
- Block 37 also turns the six `INSERT OR IGNORE ... SELECT` copies into `INSERT ... SELECT ... WHERE true ON CONFLICT DO
  NOTHING` (`WHERE true` resolves SQLite's parse ambiguity between a `SELECT` and an upsert); the seventh,
  `_COPY_MATCH_DECISIONS`, a plain `INSERT ... SELECT DISTINCT ... WHERE NOT EXISTS`, already raises. A duplicate is
  still skipped, while a row breaking a `CHECK` or a `NOT NULL` raises (probed on SQLite 3.49.1, the host's, and 3.46.1,
  the image's), so the existing sign `CHECK` on `session_received_bytes` now refuses too. The copier runs each copy
  statement so that a refusal the schema raises names the source and the table, and the sources already merged; SQLite's
  own text names no row. With `--output`, such a refusal leaves the output holding the earlier sources, and the message
  says to go on with `--into` it. `CatalogCopier`'s docstring and `MergeError`'s state D9 and D11.
  Pitfalls for block 37: `tests/support/catalog_rows.py`'s `insert_source_variant` sets a stand-in hash
  (`blake2b(repr(...))`), so every merge test built on `make_catalog` would be refused until it uses the store's own
  hash; the store hashes `connectable` as a JSON boolean while it stores 0 or 1, so the SQL function must turn it back
  into a boolean before hashing; `test_t16_merger_wraps_source_copy_in_a_transaction`'s broken source now fails the
  check before any copy, so its mid-copy failure needs another trigger (a destination trigger, for one).
  **Left to the STRICT lot**, which its backlog entry and the handoff must name, since this lot relies on it to close
  the gap: a value of the wrong type in any column (a text or a real in an `INTEGER` column, a blob in a `TEXT` one), a
  negative size, count, duration or bitrate, a `tier` outside `DecisionTier` and `retracted`, an instant in micros
  outside `datetime`'s range. The closing block extends the STRICT entry with sign and closed-set `CHECK`s "so `merge`
  refuses through the schema what D9 of `agents/specs/2026-10-30-values-checked-at-the-boundary.md` left to it (types,
  signs, tiers, instants)", and moves it under "Must be done before the next release".
- **D10.** `_SELECT_DOWNLOAD_DECISIONS` (`sqlite_decision_store.py`) keeps reading every node's decisions; the
  `DecisionReader` port's docstring states it, with D10's reason, and one download-candidate test sets another node's
  decision, so no later lot filters it as a bug. Block 35.
- **Documents.** `AGENTS.md`'s design invariants gain: "the node supports UTF-8 text only; a text that is not valid
  UTF-8 is refused where the operator wrote it and replaced with U+FFFD where a network sent it". Its amuleapi
  gotchas gain: amuleapi writes valid UTF-8 only, a lone surrogate as U+FFFD; every integer the mapper stores is a
  signed 64-bit cast of an unsigned field, a search result's or a link's size bounded by 256 GiB; the mapper checks
  anyway, for D3. The skipped-results metric that counts a dropped size is set in `domain/observability/policy.py`.
- **Pitfall for blocks 20 and 30.** An editing tool may decode a JSON-style escaped pair written in a file into the
  character it spells: check the bytes of every test fixture holding a surrogate escape.

## Appendix B. Acceptance, in detail

1. `mapping.py` maps a search result whose source count is `-1` or 2\*\*63 to a `ReportedFile` whose count is 0, one
   whose duration or bitrate is `-1` to `None`, and drops one whose size is `-1` or 2\*\*63; a source whose
   `downloaded_bytes_session` is `-1` to a `session_received_bytes` of 0; a download whose `completed_bytes` is `-1`
   or whose size is 2\*\*63 to 0. It maps a filename, a source name, the software, a `raw_metadata` key, value and
   tuple element holding a lone `\ud800` to texts holding U+FFFD, and a filename holding a pair left as two
   surrogates (the bytes `ED A0 BD ED B8 80`) to one holding two U+FFFD. On `main` each of them passes through as it
   came. Block 10's pull request carries the new tests' failing run on `main`'s mapper and their passing run at its
   tip.
2. Each type of D3 raises `ValueError` for a lone surrogate and for a surrogate pair in each of its text fields (a
   `raw_metadata` key, text and tuple element among them) and for `-1` and 2\*\*63 in each of its integer fields, and
   builds with 0, 2\*\*63 - 1 and `None` where the field is optional, and with U+FFFD and U+1F600 (one code point) in
   each text field: one parametrized case per field and position, in its own tests; block 20's pull request carries
   one failing run before the `__post_init__`s.
3. With `AMULE_API_PASSWORD` set and copies of `deploy/*.yml`, `uv run python -m p2pwatch validate-config` exits 1 and
   prints one line naming the file and the key path for text that is not valid UTF-8 in any file (D4), the value for
   a control character (D5, as targets.yml's and matcher.yml's messages do), the variable for the environment (D4):
   on a keyword `"\ud800"`, a matcher.yml rule name `"\ud800"`, a keyword `"\ud83d\ude00"`, a target title `"\ud800"`, a
   letter `"a\x1fb"`, a letter holding `"\x85"` and a rule name holding `"\t"`, and names the variable when
   `crawler.yml` interpolates one whose value is not valid UTF-8; each of the eight exits 0 on `main`. Block 30's pull
   request carries the sixteen runs.
4. A source catalog at the current schema, its clean rows written through the real stores (a source variant's
   `connectable` true, false and absent), then seeded one value at a time: a filename of bytes that are not UTF-8, an
   escaped `\ud800` in an observation variant's `raw_metadata`, a `raw_metadata` that is not JSON, a U+001F in a
   `target_id`, a `\t` in a `rule_name` (block 35); a `file_id` its `native_id` does not derive, a `content_hash` that
   is not its variant's, in each variant table, and a source variant's `role` `'bogus'` in a source built without that
   `CHECK` (block 37). For each, `uv run python -m p2pwatch merge` exits 2 naming the source and the table (and the
   column for a check), in both modes: with `--output`, no file is left; with `--into`, the destination's
   `database_digest` is unchanged. On `main` each exits 0, the `'bogus'` row dropped in silence. The clean source merges
   as before, and a merge of the clean source then the `'bogus'` one leaves the clean one merged and names it (D11).
   Blocks 35 and 37 carry their runs.

## Appendix C. Facts

From `boundary-values-inventory`, the three spec reviews (`.reviews/values-at-the-boundary-spec*.md`) and the lead's
reading, 2026-10-30. amuled's sources: amule-org/amule at `909d304d` (the pinned 3.1.0, also v4.1.0's), read with
`gh api 'repos/amule-org/amule/contents/<path>?ref=909d304d993ee07df6c6f6acf501a6d791d53666'`.

- **How invalid UTF-8 enters Python.** A `str` that is not valid UTF-8 holds a surrogate (U+D800 to U+DFFF), half of
  a UTF-16 character, which no UTF-8 text contains. JSON's and YAML's `\uXXXX` escapes count in UTF-16 units, so a
  valid UTF-8 file can still spell one; `json.loads` decodes bytes with `surrogatepass`, and `os.environ` decodes a
  variable with `surrogateescape`, so bytes that are not UTF-8 enter as surrogates. Python fails only when it writes
  such a text out: sqlite3, `httpx` and Starlette raise `UnicodeEncodeError`.
- **What amuleapi sends.** `CJsonWriter::WriteEscapedString` (`src/libwebcommon/JsonWriter.cpp`) recombines a
  surrogate pair and writes a lone surrogate as U+FFFD. Every integer the mapper stores is written
  `ValueInt(static_cast<int64_t>(...))` (`src/webapi/SearchJson.cpp`, `Api.cpp`) from a `uint32` (counts, duration,
  bitrate) or a `uint64` (sizes, `completed_bytes`, `downloaded_bytes_session`), all in `src/webapi/State.h`.
  `CSearchList::AddToList` (`src/SearchList.cpp`) drops a result of size 0 or above `MAX_FILE_SIZE` (`0x4000000000`,
  256 GiB, `src/include/protocol/ed2k/Constants.h`); a server's, Kad's and a peer's shared list's results all go
  through it, and a search amuled restores from its own stored list was filtered when first received. `CED2KLink`
  (`src/ED2KLink.cpp`) refuses a link of size 0 or above it. One size goes unbounded: a download's, read back from its
  own `.part.met` at start (`src/PartFile.cpp`, `FT_FILESIZE`), which is amuled's disk, not the network.
- **What a store does with a value D3 refuses.** sqlite3 raises `UnicodeEncodeError` binding a surrogate and
  `OverflowError` binding an integer outside [-2\*\*63, 2\*\*63 - 1], neither a `sqlite3.Error`, so
  `wrap_sqlite_errors` lets both through and every `except StoreError` with it (`cataloguer.py`, `source_watcher.py`,
  `download_tracker.py`), ending the `asyncio.TaskGroup`s; the catalog stores raise earlier, at the content hash's
  `.encode()`. A negative integer is stored silently, except `session_received_bytes`, whose sign `CHECK`
  (`migrations/catalog/0011`, renamed by `0012`) logs a `PersistenceError`.
- **No stored row breaks D3.** `observation_from_row` (`persistence_sqlite/observation_read.py`) rebuilds a
  `ReportedFile` on every catalog read (the files page, the reevaluation, the download loop). A column cannot hold a
  surrogate (sqlite3 refuses the bind) nor an integer of 2\*\*63; `raw_metadata`, JSON text, could hold an escaped
  surrogate that a read decodes, but none ever arrived, amuleapi writing none and the EC era before it (until
  2026-09-22) decoding with `errors="replace"` (`mule_ec/codec.py`, commit `7075e3d4`); and amuled never sent a
  negative integer (above). The operator's catalog (`/home/geoffrey/Projets/mulewatch/data/catalog.db`, schema 5,
  opened `?mode=ro`, 2026-10-30) confirms it with two queries: `SELECT count(*), sum(size_bytes<0),
  sum(source_count<0), sum(complete_source_count<0), sum(media_length_sec<0), sum(bitrate_kbps<0) FROM
  file_observations` gave 15,763,676 rows and five zeros (and `files` 2,162 rows, none negative); the same rows'
  `raw_meta` holding a `\ud8` to `\udf` escape, by `instr(lower(raw_meta), ...)`, gave 0, and `source_observations`
  is empty.
- **The mapper's readers** (`adapters/driven/amule_api/mapping.py`): `_string` (filename, codec, file type, status,
  source name, software, daemon version); `_int_or_zero` (a download's `bytes_done` and `size_bytes`,
  `session_received_bytes`, the source counts, the waiting counts); `_optional_int` (duration, bitrate, `ecid`,
  `ed2k_user_id`); the inline check of a search result's `size_bytes`; `_render` and `_meta_value` for
  `raw_metadata`, whose source values may be tuples of texts (`domain/source.py`). None bounds an integer or filters
  a text; the hash (`_hash_hex`) and the contact point (`parse_contact_point`) are checked.
- **The types of D3**: `ReportedFile` (`domain/observation.py`: `filename`, `keyword`, `raw_metadata`; `size_bytes`,
  `source_count`, `duration_seconds`, `bitrate_kbps`), `SourceReading` (`domain/source.py`: `source_name`,
  `software`, `raw_metadata`; `session_received_bytes`), `DownloadStatus` (`domain/download/status.py`: `bytes_done`,
  `size_bytes`), `ClientStatus` (`domain/status_reading.py`: `version`). None has a `__post_init__` today.
- **Config.** PyYAML turns `"\ud800"`, `"\U0000d800"` and `"\ud83d\ude00"` into surrogates (the pair is not recombined)
  and `"x\x1fy"` into a control character. A keyword reaches `httpx`'s JSON body, which raises `UnicodeEncodeError`
  (no `httpx.HTTPError`, so `_send` lets it through), and `_kad_word`'s `.encode()`; a target letter
  (`catalog_matching/domain/validation.py`, `str()` only) and a rule name (non-empty only) reach `match_decisions`
  and `_split_concat` (`sqlite_catalog_file_reader.py`), whose `zip(strict=True)` raises `ValueError` on the files
  page when one holds U+001F. `crawl` and `validate-config` share `read_targets`
  (`adapters/driven/config/crawler_config.py`) and `load_yaml`; `interpolate_document` runs after `load_yaml`.
- **aMule 3.2.0** (`gh release view 3.2.0 -R amule-org/amule`, 2026-10-28): 15 advisories, every one also in 3.1.0.
- **`merge` today** (`merge-boundary-inventory`, probes in the session's scratchpad, 2026-10-31). `SqliteCatalogCopier`
  attaches each source, refuses a `user_version` other than the destination's, then copies six tables by `INSERT OR
  IGNORE ... SELECT` and the decisions by `INSERT ... SELECT DISTINCT ... WHERE NOT EXISTS`, in one transaction per
  source; Python never decodes a row. Merged without error and failing on read afterwards: a text of bytes that are not
  UTF-8 (`OperationalError`), an escaped surrogate in `raw_metadata` (`ValueError`, D3), a `raw_metadata` that is not
  JSON (`JSONDecodeError`), a text in an `INTEGER` column (`TypeError`), a negative size (`ValueError`); merged and
  never re-checked: an unknown `tier`, a U+001F in a `target_id` (the files page's `_split_concat`), a `file_id` not
  derived from its key (it then blocks the node's own writes of that key), a real such as 3.5 in an `INTEGER` column.
  `INSERT OR IGNORE` skips a row breaking a destination `CHECK` or `NOT NULL`, and the observations of a skipped variant
  with it: a source row `role 'bogus'` merged 0 rows, exit 0; `ON CONFLICT DO NOTHING` skips the duplicate and raises on
  the `CHECK` (lead's probe). Already refused: a source that cannot be attached (UTF-16 included), another schema
  version, a foreign key violation. D9's own checks scale with the variants, not the observations: per 20,000 variants,
  the UTF-8 check of four text columns about 14 ms, `raw_metadata`'s JSON 14 to 33 ms, `file_id` 4 ms, `content_hash` 64
  ms; reading every observation back through `observation_from_row` would take about 115 s for 15.8 million. SQLite
  3.49.1 has no UTF-8 validator: `json_valid` accepts every invalid case probed, and a function over `CAST(x AS BLOB)`
  decoding strictly refuses them all. A merged catalog's `download` decisions drive the download loop
  (`_SELECT_DOWNLOAD_DECISIONS` reads every node's), kept by D10.

## Appendix D. The round-trip contracts

What the Discuss of 2026-10-30 settled for the lot that takes "Round-trip contracts", and what it corrects in
Appendix B of `agents/specs/2026-10-29-rows-read-by-column-name.md`.

- **Before the v5 tag, after this lot, before "Test quality"** (operator, 2026-10-30). *A guard is weighed by the
  defects it will prevent, not only those already found; the contracts rewrite the persistence adapters' tests, which
  "Test quality" would otherwise prune first.*
- **Values drawn with the standard library's `random.Random`, one draw per test, seeded from the test's node id.**
  *Catching a swap needs two columns with distinct values, which one draw gives; Hypothesis's hundred examples and
  shrinking add nothing here, and would need a new dependency, a factory in place of the contracts' fixture (a
  function-scoped fixture is built once per test, not per example) and a much longer mutmut run. A seed from the node
  id keeps each test's values fixed whatever the order or the selection; `test_engine_properties.py` in matching
  already draws with a constant seed.*
- **The values a draw avoids**: a text that is not valid UTF-8 (a surrogate, paired or not) and an integer outside
  [-2\*\*63, 2\*\*63) in any field, which every store refuses (a `DecisionRecord`'s target id or a backoff's keyword as
  much as D3's types); a negative integer in a field D3 checks; a control character in a target id or a rule name
  (D5), which `DecisionRecord` and the decision writer still take; the `CHECK`s `attempts >= 1` and
  `delay_seconds >= 0` (`migrations/local/0011_backoff_states_table.sql`); a non-canonical native id, which no
  production path builds (`_hash_hex`, `SourceKey`, `require_canonical_native_id`).
- **Corrections**: `_split_concat` lives in `sqlite_catalog_file_reader.py`, not the decision store, which stores a
  U+001F unharmed; the `CHECK`s `last_seen_at >= first_seen_at` and `received_bytes >= 0` left with `source_ranges`
  (`migrations/catalog/0011`); `transfer_counter >= 0` is now `session_received_bytes >= 0`.
