# Values checked at the boundary

Tier Spec. Discussed with the operator on 2026-10-30. Found while discussing the round-trip contracts. Ships before the
v5 tag (D7).

## 1. In short

The node supports UTF-8 text only, but nothing enforces it, nor the range of the integers it stores. Today only the
operator's config breaks the rule: a keyword that is not valid UTF-8 stops the crawler at its first search, and a unit
separator in a target letter or a rule name breaks the files page. amuled already sends valid values; the next mapper
(stage 5), or a change of amuleapi's format, may not, and the store would then stop the process.

The lot gives every boundary one rule: the domain refuses a value it cannot carry, the mapper cleans what a network
sends, and the config refuses what the operator wrote.

## 2. What the operator will see

- `validate-config` and `crawl` refuse a config file holding text that is not valid UTF-8, a control character in a
  target letter or a rule name, or an environment variable that is not valid UTF-8; each error says where.
- Nothing else changes: amuled's answers already pass every new check.

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

The operator decided each of D1 to D8 on 2026-10-30; the names D3 introduces are in Appendix A.

## 4. Acceptance

1. The mapper cleans each kind of invalid text and integer of D1 and D2, which `main` lets through (Appendix B).
2. Each domain value of D3 refuses each invalid text and integer, and accepts the limits and valid non-ASCII text.
3. `validate-config` refuses each invalid config of D4 and D5 and says where, where `main` accepts it.
4. `uv run poe check` passes at each block's tip.

## 5. Blocks

Estimates by `boundary-values-estimates` (Sonnet, 2026-10-30). The bound is checked after committing.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `fix/amuleapi-values-cleaned` | D1, D2 | 175, 4 |
| 20 | `feat/domain-value-bounds` | D3, D6 | 285, 15 |
| 30 | `fix/config-refuses-invalid-text` | D4, D5 | 140, 8 |
| 40 | `docs/wrap-values-at-the-boundary` | closing | 20, 2 |

The mapper comes first, so nothing arriving is refused once the domain starts refusing; block 30 reuses the domain's
check.

## 6. Documents

- `AGENTS.md`: the invariant "UTF-8 text only", and what amuleapi really sends (block 40).
- `docs/migration-4x.md`: the config values now refused (block 30).
- Stage 1's D16 and the umbrella spec: a correction beside each line D7 revokes (block 40).

## 7. Limits and scope

### Accepted limits

- **A text D1 cleans is no longer the sender's**: two names differing only by invalid UTF-8 read the same.
- **A value D1 or D2 cleans leaves no trace**, except a dropped size, which a metric counts.
- **The integers inside a file's raw metadata stay unchecked**: they are stored as text and read by no decision.

### Backlog

With block 10's first commit, as agreed on 2026-10-30: "aMule 3.2.0 pinned" added and "Round-trip contracts" moved,
both under "Must be done before the next release" (Appendix A, D7).

### Adjacent backlog items

- "Round-trip contracts": the next lot, whose draws D3 defines (Appendix D); it stays open.
- "Multi network", stage 5: its mappers inherit D3's guard; it stays open.
- "Every catalog table STRICT": a guarantee on a value's type, not its range or its encoding; it stays open.
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
