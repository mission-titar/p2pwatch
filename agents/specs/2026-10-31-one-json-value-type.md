# One domain type for arbitrary JSON

Tier Spec. Discussed with the operator on 2026-10-31, from `BACKLOG.md`'s "One domain type for arbitrary JSON".

## 1. In short

The raw metadata of a file and of a source is one concept, a JSON object of what the network sent that no field
consumes. The code holds it in two hand-written types, `RawMetadata` and `SourceMetadata`, and stores it in two forms,
an array of `[name, value]` pairs for a file and an object with sorted keys for a source. No code reads a field of it:
it is produced by the mappers, stored, hashed into its variant's `content_hash`, checked by `merge` and shown by the
SQL console.

The lot types both by one opaque value, `JsonText`, the canonical text of a JSON object, and stores both in that one
form. No migration and no pass over the rows is added: a file's new form is written inside the rewrite v5's migrations
already make. Where the backlog item kept the stored bytes, the operator chose one form (D3).

## 2. What the operator will see

- `merge` refuses a source catalog whose file or source metadata is not the canonical JSON text of an object (D6).
- In the SQL console, a file's `raw_metadata` is an object whose network names sit under `unmapped` (D4).
- Nothing else: amuled's answers, the operator's catalog and every page read as before.

## 3. Decisions

### The concept

- **D1. `JsonText`, a frozen value holding the canonical text of a JSON object, its keys sorted, its text valid UTF-8,
  no `NaN` nor infinity; built from that text, `JsonText(text=...)`, or from a mapping, `JsonText.from_object(...)`.**
  *No code reads inside the metadata, so the domain needs its canonical text, not its structure: equal content gives
  equal text, hence one variant, and equality is the text's, exact. A code that one day reads a field looks it up and
  checks its type, which parsing the text does as well.* (Operator, over a recursive `JsonValue` type, then over a
  `NewType`, which any code could build from an unchecked text, 2026-10-31.)
- **D2. `raw_metadata` is a `JsonText` on both `ReportedFile` and `SourceReading`; `RawMetadata`, `SourceMetadata` and
  their two UTF-8 walks are deleted.** *The metadata is a JSON object: one concept, one type, which guards what the
  walks guarded.* `ReportedFile` keeps a default, as today: the empty object.

### The stored form

- **D3. Every stored metadata is a `JsonText`, which migration 0007 writes too.** *One form for one concept, and
  nothing reads the wire order. 0007 is in no release and no catalog to keep has passed it (operator), so changing
  what it writes adds no pass over the rows (Appendix B).* A source's stored bytes, already this form, do not move.
  Where a v4 row repeats a name, which v4 allowed, 0007 keeps its last value, as `json.loads` does: *the upgrade
  never stops on such a row, and the operator's catalog holds none (Appendix B).* (Operator, over refusing the row.)
- **D4. A file's metadata keeps the names its mapper derives at its first level, and under `unmapped` what the
  client's API sent that no field consumes: on eD2k, the result's keys and, when it holds one no field consumes, its
  `media` object, every value rendered as text as v4 stored it.** *Flattened as today, a key amuleapi may add (a
  top-level `codec`, or one spelled `media.title`) repeats a name the mapper chose, and a JSON object keeps one value
  per name. Kept apart, no name the network sends can meet one of ours; `unmapped` says what its members are, what no
  field maps, not one API's structure, so stage 5's mappers fill it alike. Values stay text, and `media` appears only
  when it holds such a key, so a mapped result and 0007's fold of its v4 row write the same text (stage 1's D11),
  unless the result held a top-level key spelled `media.<k>`, which v4 could not tell from `media`'s (section 7).*
  (Operator, over the mapper's names winning, which would drop the colliding key; name: operator.) A source's metadata
  stays flat: its mapper keeps only the keys it names, from two disjoint lists.

### The guards

- **D5. A `JsonText` refuses, when it is built, a text that is not a JSON object, holds invalid UTF-8 or a number
  that is not finite, or that parsed and written back would not be the same text.** *Checked in the value itself,
  the rule holds for every `JsonText`, whoever builds it: a mapper, the reader of a stored row, `merge`. The node
  supports UTF-8 text only (`AGENTS.md`) and RFC 8259 admits no `NaN` nor infinity; the write-back refuses every other
  spelling, an unsorted or repeated name, and the text `from_object` writes for a nested name that is not text
  (`{2: .., 10: ..}`, sorted as numbers, not as the text they become).* A nesting `json.loads` cannot parse, past about
  10 000 levels, is refused, not raised. Its error says "a JSON text", no longer its holder: no production path reads
  the message.
- **D6. `merge` refuses a source catalog whose file or source metadata is not a `JsonText`.** *A merged row can never
  be deleted, and one the reader refuses would stop the reevaluation at start and the files page, while one in another
  spelling would give a second variant to the same content; today's check accepts all of them but the lone
  surrogate.*

### Where it lives

- **D7. `JsonText` wraps the `json` module, in `domain/json_text.py`; the domain may import `json`'s `loads` and
  `dumps` only.** *Both are pure, parsing and writing a string, never a file, as `configparser` in `p2pwatch_amule`'s
  domain; the limit keeps out `load` and `dump`, which take a file, as `io` is limited to `StringIO`. The guards then
  hold in one place, and stage 5's mappers, which may not import `persistence_sqlite`, will use them.*

The operator decided D1 to D7 on 2026-10-31.

## 4. Acceptance

1. `JsonText.from_object` writes keys sorted, and refuses `NaN`, an infinity, a lone surrogate in a name, in a text
   and in a text nested in a list or an object, and a nested object named by `2` and `10`.
2. `JsonText(text=...)` refuses a text that is not an object, an object with unsorted or repeated names, one spelled
   with other spacing or escapes, `NaN`, `1e999`, an escaped lone surrogate and a nesting of 10 000 levels, each with
   a `ValueError`.
3. The stored bytes are asserted against literal strings, never against the code the lot changes: the source point
   store's literal, extended with a boolean, an integer and a `null`, which `main`'s bytes also pass; the observation
   store's; migration 0007's.
4. The file mapper stores a top-level `codec`, a top-level `complete_source_count` and a top-level `media.title` beside
   a `media` object holding `title`, each under `unmapped`, where `main` repeats the name; 0007 writes a v4 row holding
   `media.title`, `rating` and `0x0308` as D4 states, keeps the last value of `[["0x0308", "0"], ["0x0308", "1"]]`,
   and a mapped result reuses the variant 0007 built from its v4 row.
5. `merge` refuses, in both its modes, a source catalog holding each text of acceptance 2 as a file's or a source's
   metadata, and on the file side a `[name, value]` pairs text; `main` merges the unsorted, repeated, respaced,
   escaped, `NaN` and `1e999` source metadata, and the pairs text.
6. After block 20, `git grep -nw -e RawMetadata -e SourceMetadata -e _metadata_texts -e _is_metadata_pairs -e
   _is_metadata_object -- packages/` prints nothing.
7. `uv run poe check` passes at each block's tip.

## 5. Blocks

The source side comes first: its stored bytes do not move. Block 20 holds the file side whole, since a mapper or a
migration writing a form the merge refuses would leave a block incoherent. Estimates by `json-text-estimates`
(Sonnet), 2026-10-31; the bound is checked after committing.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `refactor/json-text-for-source-metadata` | D1, D5, D7; D2, D3, D6 for `SourceReading` | 350, 17 |
| 20 | `refactor/json-text-for-file-metadata` | D4; D2, D3, D6 for `ReportedFile` | 380, 15 |
| 30 | `docs/wrap-one-json-text` | closing, and section 6's two operator documents | 20, 3 |

## 6. Documents

- `AGENTS.md`, "No I/O in the core": `json` in the domain, limited as D7 states (block 10).
- `docs/operate.md`, the catalog merge: the metadata it refuses (block 30, since v5 is unreleased).
- `docs/migration-4x.md`: a file's `raw_metadata` becomes an object, its network's names under `unmapped`, so a SQL
  console query's JSON path changes (block 30).
- The closing block's handoff. No glossary line: `AGENTS.md`'s glossary takes only the terms the operator asks for.

## 7. Limits and scope

### Accepted limits

- **A result holding a top-level key spelled `media.<k>` beside `media`'s own `<k>` gets a second variant on upgrade**
  (D4): v4 stored both under one name, which 0007 puts under `media`. amuleapi sends no such key, and the operator's
  three `media.<k>` names are `media`'s (Appendix B).
- **The integers inside metadata stay unchecked**, as the lot "Values checked at the boundary" left them: stored as
  JSON text and read by no decision.

### Backlog

The closing block deletes "One domain type for arbitrary JSON".

### Adjacent backlog items

- "Round-trip contracts": the next lot; a drawn metadata compares as text, exactly; it stays open.
- "Every catalog table STRICT": a column's type, not the JSON inside it; corrected on 2026-10-31 to be declared in the
  unreleased migrations' `CREATE TABLE`s, as D3 uses 0007; it stays open.
- "Multi network", stage 5: its mappers fill `unmapped` and build a `JsonText` with `JsonText.from_object`; it stays open.
- The other items are unrelated and stay open.

## Appendix A. Design

Paths under `packages/crawler/src/p2pwatch/`.

- **The type** (`domain/json_text.py`): `JsonText`, a `kw_only` frozen dataclass with one field, `text`, whose
  `__post_init__` holds D5: `json.loads`, its `RecursionError` turned into `ValueError` (a `JSONDecodeError` is already
  one), an object required, then `json.dumps(..., ensure_ascii=False, sort_keys=True, allow_nan=False)` of what it
  parsed, today's source form, compared with `text`, and `require_well_formed_text` on it. The classmethod
  `from_object(json_object)` takes a `Mapping[str, object]` and returns `cls(text=...)` of the same `json.dumps`, so the
  guard checks it. `ReportedFile.raw_metadata`'s default is `JsonText(text="{}")`. `p2pwatch.domain` is one tach
  module, so the new file needs no declaration.
- **The import rules**: `ast-grep/rules/domain-imports.yml` gains `json`, `core-import-names.yml` its two names,
  each with a valid case in `ast-grep/tests/`.
- **The producers**: the source mapper (`_source_metadata` builds a `dict`, its tuple of texts written as a list as
  today), the file mapper and `fold_raw_metadata` (`domain/observation.py`), which takes the `unmapped` mapping and
  returns the file's `JsonText`. The mapper keeps replacing surrogates in names (`replace_surrogates`), since a
  `ValueError` raised in `_map_result` would escape the search. The file mapper keeps rendering every value to text
  (`_render`), so a mapped result
  and 0007's fold of its v4 row agree (stage 1's D11, `test_migration_0007.py`).
- **The stores and the reader**: `SqliteSourcePointStore` and `SqliteObservationStore` write `raw_metadata.text`;
  `observation_from_row` (`observation_read.py`) reads it back as `JsonText(text=row["raw_metadata"])`.
- **Migration 0007**: its SQL function `fold_raw_meta` (`persistence_sqlite/variants.py`) reads v4's pairs into a
  `dict`, which keeps the last value of a repeated name, puts `media.<k>` under `unmapped`'s `media` and every other
  name, EC tags included, under `unmapped`, and folds. No `.sql` file changes. The docstrings stating the old form
  change with it: `variants.py`'s first lines (a change of serialization needs a migration), its comment "0007, which
  never changes", `sqlite_observation_store.py`'s (a list of pairs, wire order, no sorting), `domain/observation.py`'s
  first lines and `fold_raw_metadata`'s (pairs), and `_raw_metadata`'s (wire order).
- **The merge** (`sqlite_catalog_copier.py`): each side's metadata is checked by building a `JsonText` from it, the
  source side in block 10, the file side in block 20, where `_is_metadata_pairs` goes; one problem text, "is not the
  canonical JSON text of an object", replaces `_NOT_PAIRS` and `_NOT_OBJECT`, and the module docstring's "a value the
  node could not read back" becomes "a value the node would not write".
- **The tests**: `test_source_watcher.py`'s `SourceReading`s take a `JsonText` in block 10; the support writes the
  object form from block 20 (`insert_observation` in `tests/support/catalog_rows.py`, `older_catalog.py`'s versions 8
  to 13, and `test_migration_0008.py`'s rows where the reader now checks them), and `test_describe_file.py`'s
  `ReportedFile` takes a `JsonText`; the owners' tests of a surrogate in
  `raw_metadata` move to `JsonText`'s own tests. Today's agreement case of `test_migration_0007.py` (a `media`
  holding only mapped keys) stays beside acceptance 4's.

## Appendix B. Why D3 adds no pass over the rows

- Migrations 0006 to 0015 are in no release: `git ls-tree` of `v4.1.0`, the newest tag, lists catalog migrations 0001
  to 0005. No catalog to keep has passed 0007 (operator, 2026-10-31).
- 0007 builds the file variants from v4's rows through `fold_raw_meta`; 0008 recomputes every `content_hash` from the
  text 0007 wrote; among 0009 to 0015, none reads or rehashes it (0013 renames the column). Changing
  `fold_raw_meta`'s output is enough.
- On a copy of the operator's catalog (version 5, 15.7 M observations, 2026-10-31), the 22 distinct stored metadata
  repeat no name, before the fold and after it, every value is text, and they stay 22 once D4 folds them: no two
  variants merge. Their names spelled `media.<k>` are `media.album`, `media.artist` and `media.title`, keys of
  amuleapi's `media` object, so D4's move puts each back where amuleapi sent it.
- v4's source rows never reach a stored source metadata: 0006 drops them.
