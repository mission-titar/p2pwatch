# Identifiers typed apart from bare strings

Tier Spec. Discussed with the operator on 2026-10-28. Ships the `BACKLOG.md` entry "Identifiers typed apart from
bare strings" (D2 of `agents/specs/2026-10-09-stage2-search-download-status-ports.md`), widened to two more pairs.

The body reads in five minutes. The appendices hold what the teammates need: where each identifier enters, what
stays raw, the commands and the counts.

## 1. In short

Nine identifiers travel as a bare `str`, `bytes` or `int`, so mypy cannot tell one from another: a channel passed
where a client name is expected, or a group id where a user id is, type-checks. Each becomes a type of its own,
so mypy refuses the swap. Stage 5 multiplies clients and channels; its adapters will be written against the types
from the start.

| Identifier | Type | Raw type | Package |
|---|---|---|---|
| `client_name`, `channel`, `node_id`, `keyword` | `ClientName`, `Channel`, `NodeId`, `Keyword` | `str` | `p2pwatch` |
| `file_id`, `source_id` | `FileId`, `SourceId` | `bytes` | `p2pwatch` |
| `target_id` | `TargetId` | `str` | `catalog_matching` |
| `uid`, `gid` | `Uid`, `Gid` | `int` | `p2pwatch_amule` |

## 2. What the operator will see

Nothing: no page, metric, notification, config key or database changes. The types exist for mypy only.

## 3. Decisions

- **D1. Each identifier is a `NewType` over its raw type.** mypy refuses a swap and a bare literal, the value costs
  nothing at runtime and still flows wherever its raw type is enough. *A frozen value class would also make a
  forgotten wrap fail a round-trip test, but a forgotten wrap breaks nothing, the value being the right one; the
  harmful mistake, the wrong column wrapped, escapes both. The value class's price, an object per value and an
  unwrap at every exit, buys nothing against the errors that matter (operator, 2026-10-28). (Corrected: the first
  draft said a value class added no guarantee at all.)*
- **D2. The type is the variable's name in CamelCase.** `node_id` is a `NodeId`, `channel` a `Channel`. *One
  concept, one name, the type included; `Channel` holds only a name, which suits an opaque channel.*
- **D3. One `identifiers.py` per package, in its domain.** `p2pwatch`'s holds six types, `p2pwatch_amule`'s two,
  `catalog_matching`'s one. *The types are declarations without behaviour, so one file shows them all.
  `TargetId` lives in `catalog_matching`, which produces it and cannot import the crawler.*
- **D4. An identifier is typed where it enters the code**, then carried by every annotation. *mypy then follows the
  value from its entry to its last reader. Where the source is untyped (an SQLite row, a URL parameter), mypy cannot
  check the wrap: section 7.*
- **D5. `SearchKeyword` goes; `Keyword` replaces it.** *A one-field wrapper already half-played the role; two types
  for one concept break "one concept, one name".*
- **D6. No identifier is invented as a placeholder.** A completed download with no known target carries no target,
  instead of a target named `unknown`; the notification still writes `unknown`. *Typed, the placeholder would be a
  `TargetId` naming no target. In normal operation the case never occurs, so no output changes.*
- **D7. A webui name holding an identifier's hex text ends in `_hex`.** *`file_id` is a `FileId` everywhere else;
  one name, one concept. The URLs do not change.*
- **D8. A webui display keeps plain text.** *A display's values are already text, and a typed identifier flows into
  one unchanged.*
- **D9. Tests wrap their literals** (`NodeId("node-a")`). *mypy checks the tests strictly; the tests state the types
  the code promises.*
- **D10. `PUID` and `PGID` each get their own parser.** *One parser for both would return a bare `int`, so the swap
  the types exist for would stay open at the one place both are read.*

### Conventions

Block 10 adds to `AGENTS.md`'s Naming: "**An identifier is a `NewType`** named after its variable in CamelCase, in
its package's `domain/identifiers.py`, typed where it enters (`NodeId`, `Channel`)." It adds `uid` and `gid`
(POSIX's user and group ids) to the allowed abbreviations.

## 4. Acceptance

1. Each package's identifier test makes mypy fail if two of its types, or a type and a bare literal, stop being told
   apart (appendix C).
2. A completed download with no known target carries no target, logs `unknown` and notifies `unknown` (block 30).
3. No parameter or field named after an identifier keeps its raw type, except in the webui's displays and the SQL
   functions (appendix C).
4. No return type or dictionary key of an identifier keeps its raw type (appendix C).
5. `SearchKeyword` no longer exists.
6. No webui name holding hex text is `file_id` or `source_id`, routes included.

## 5. Blocks

Estimates by `typed-ids-estimates` (Sonnet, 2026-10-28).

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `refactor/uid-gid-settings` | `Uid`, `Gid` in the settings, D10, the conventions | 55, 7 |
| 20 | `refactor/uid-gid-ports` | `Uid`, `Gid` in the four ports | 65, 19 |
| 30 | `refactor/completed-download-without-target` | D6 | 45, 6 |
| 40 | `refactor/target-id-type` | `TargetId` | 390, 61 |
| 50 | `refactor/node-id-type` | `NodeId` | 525, 79 |
| 60 | `refactor/client-name-and-channel-types` | `ClientName`, `Channel` | 250, 46 |
| 70 | `refactor/keyword-type` | `Keyword`, D5 | 160, 34 |
| 80 | `refactor/webui-hex-names` | D7 | 15, 6 |
| 90 | `refactor/file-id-type` | `FileId` | 50, 12 |
| 100 | `refactor/source-id-type` | `SourceId`; drafts the handoff | 45, 10 |
| 110 | `docs/typed-identifiers-wrap` | closing: the holistic findings, `BACKLOG.md`, the handoff | |

- **Blocks 40 to 70 pass 20 files, block 50 also 500 lines, under the mechanical exemption** (operator,
  2026-10-28). The exemption is stretched: besides annotations, they add their types and identifier tests, wrap at
  the entry points and edit `tach.toml`. *Splitting a type by flow, producers before consumers, keeps each half
  green but spreads one type's change over two reviews; block 60 split by type would still leave each half near 20
  files.*
- Block 30 is a `refactor`: no output changes in normal operation (D6).

The order: the smallest package first, so the convention lands with the least code; the placeholder removed
before `TargetId`, so the type never holds it; `TargetId` before the crawler's own types; the hex names before
`FileId`.

## 6. Documents

- `AGENTS.md`: the conventions (block 10); the route `/sources/{source_id_hex}` in the WebUI row (block 80).
- `docs/operate.md` keeps `/files/{file_id}` and `/sources/{source_id}`: they show the operator a URL's shape, which
  does not change.

## 7. Limits and scope

### Accepted limits

- **A wrap from an untyped source is unchecked.** An SQLite row and a URL parameter are `Any` to mypy, so a reader
  that wraps the wrong column, or forgets the wrap, passes. A forgotten wrap is harmless (D1); the wrong column is
  the new Debt entry below, a lot of its own (operator, 2026-10-28).
- **A webui display holds plain text** (D8).

### Adjacent backlog items

- "Identifiers typed apart from bare strings": shipped, deleted by the closing block.
- Two entries the closing block adds, agreed by the operator on 2026-10-28:
  - under "Debt": "**Rows read by column name**: every reader of `persistence_sqlite` reads a column by its name,
    not its index, and every round-trip test seeds distinct values in fields of one type, so a shifted or swapped
    column fails the gate. Section 7 of `agents/specs/2026-10-28-typed-identifiers.md`."
  - under "Technical improvements": "**Keyword-only calls**: ruff's `PLR0917` at one positional parameter and
    `kw_only=True` on every dataclass, so no call passes two values by position. Section 7 of
    `agents/specs/2026-10-28-typed-identifiers.md`." Its size is in appendix D.
- "Multi network", stage 5: benefits from this lot, which it follows; nothing of it moves here.
- "Every catalog table STRICT": a schema's guarantee, which no annotation gives; it stays open.
- "Test quality", "Mutation testing in the gate", "Contract tests for the fakes of outside systems", "A generic way
  to write the tests' stubs and spies", "Adopt ty", "The Grype scan back on p2pwatch", "Sort the files view by first
  seen", "The webui in the visitor's time zone": unrelated to the identifiers' types; they stay open.

## Appendix A. Where each identifier enters

From the survey `typed-ids-boundaries` (2026-10-28); the teammate re-reads them on its block's tree.

| Type | Enters at |
|---|---|
| `Uid`, `Gid` | `p2pwatch_amule.domain.settings`: `PUID` and `PGID`, today both through `_required_id`, which D10 splits; the fields `puid`/`pgid` and the four ports' `uid`/`gid` |
| `TargetId` | `catalog_matching`'s `TargetSegment.target_id`; the crawler's SQLite readers; the webui's query and path parameters |
| `NodeId` | `Uuid4NodeIdGenerator`; `SqliteNodeIdStore`; the readers returning an observation, a source point or a node state; `CrawlerLifecycle`'s loops (`Callable[[NodeId], ...]`) |
| `ClientName` | the composition's `_AMULE_CLIENT_NAME`; `SqliteBackoffStateStore`, `SqliteNodeStateReader` |
| `Channel` | the amuleapi adapter's `_SEARCH_TYPES` keys and its status mapper; the same two SQLite adapters; `BackoffKey.channel` is `Channel \| None`, `None` the whole client |
| `Keyword` | `crawler.yml`'s `search` section, through `dedupe_keywords`; the observation reader; the amuleapi adapter's `_keywords_without_kad_word` becomes `set[Keyword]` |
| `FileId` | `FileKey.file_id`; `variants.file_id`; the webui's path parameter, through `bytes.fromhex` |
| `SourceId` | `SourceKey.source_id`; the webui's path parameter, through `bytes.fromhex` |

## Appendix B. Design notes for the teammates

- **What stays raw.** The amuleapi adapter's `_kad_next_start` keys stay `str`: they mix a Kad word and a keyword.
  `variants.content_hash` takes raw values: SQLite calls it, the migrations included. `NodeMetricLabels.texts()`
  returns text for Prometheus. `SqliteSourceReader._period_rows(key: bytes | str)` serves a file, a source and a
  source name alike. A `<Thing>Display` field stays `str` (D8).
- **D6.** `DownloadTracker._record_completion` passes `()` when `DownloadLabeler.target_titles` returns none, in
  place of `TargetTitle("unknown", "")`. The policy's log line writes `✅ download completed: unknown` for `()`;
  `AppriseNotifier`'s targets section writes `**Targets**\nunknown` (it wrote `unknown - `). The labeler falls back
  to the queued target, which `downloads.target_id NOT NULL` guarantees, so `()` arises only if a tracked row
  vanishes between the read and the label (`typed-ids-spec-review`).
- **D7.** The display field `file_id` (the files listing's link) becomes `file_id_hex`; the routes `/files/{file_id}`
  and `/sources/{source_id}` and their `path_params` keys become `file_id_hex` and `source_id_hex`, as the handlers'
  locals already are; `app.py`'s comments naming them follow.
- **`tach.toml`.** Block 20: the four amule ports and their four adapters gain `p2pwatch_amule.domain`. Block 50:
  `node_id_generator`, `node_id_reader`, `node_id_writer` and `uuid4_node_id_generator` gain `p2pwatch.domain`.
  `TargetId` needs no edit: a crawler import of `catalog_matching` crosses a distribution, which `tach check` does
  not see and `tach check-external` admits (`typed-ids-spec-review`).
- **Shared test literals** live in `tests/support/`, at the mirror of what they serve.

## Appendix C. Acceptance, as commands and tests

1. Each package's `tests/domain/test_identifiers.py` holds, under `# type: ignore[arg-type]`, a call passing a bare
   literal where each type is expected, and one passing each type where another of the same raw type is expected.
   The crawler's pairs `TargetId` with its own `str` types. mypy's strict `warn_unused_ignores` fails the gate with
   `Unused "type: ignore" comment` if a type stops being distinct. Each block adds its types' lines; block 10's are
   watched failing with `Uid = int` before the `NewType` (the reviewer's trial: 4 unused ignores, exit 1).
2. A test of `DownloadTracker` dispatches `DownloadCompleted` with `target_titles == ()` when the labeler finds none;
   a test of the policy reads `✅ download completed: unknown`; a test of the notifier reads `**Targets**\nunknown`.
   Each is watched failing first.
3. `git grep -nE "\b(client_name|channel|node_id|keyword|target_id): str\b" packages/*/src` prints lines of
   `webui/displays.py` and `persistence_sqlite/variants.py` only; `git grep -nE "\b(file_id|source_id): bytes\b"
   packages/*/src` and `git grep -nE "\b(uid|gid|puid|pgid): int\b" packages/*/src` print nothing.
4. `git grep -nE "def (new_node_id|read_node_id|channels|read_queued_target_id|target_id|file_id|source_id)\(.*->
   *(str|bytes|tuple\[str)|_by_(node_id|target_id|client_name|channel|keyword)\b.*dict\[(str|bytes)|Callable\[\[str\],
   Coroutine" packages/*/src` (one line) prints nothing.
5. `git grep -n SearchKeyword packages` prints nothing.
6. `git grep -nE "(file_id|source_id): str|\{(file_id|source_id)\}|path_params\[\"(file_id|source_id)\"\]"
   packages/crawler/src` prints nothing.

## Appendix D. Facts

On the tree at `ca871563` (2026-10-28):

- Criterion 3's commands print 126, 8 and 12 lines; criterion 4's, 18; criterion 6's, 7.
- Signatures holding two of the four crawler text identifiers as `str`: 11 classes and 5 functions (an AST walk
  over `packages/*/src`, parameters and dataclass fields); the four amule ports each take `(uid: int, gid: int)`.
- `SearchKeyword` is built by `dedupe_keywords` alone.
- mypy, root `[tool.mypy]` (`strict = true`), mypy 2.3.1, from `typed-ids-spec-review`'s trials outside the tree:
  two `NewType`s over `str` are refused for each other as an argument, a dataclass field, a `dict` index, `dict.get`
  and an assignment between `dict` types; `strict-equality` flags `==` and `in` between two of them; a plain alias
  in place of a `NewType` turns criterion 1's ignores into `Unused "type: ignore" comment`, exit 1.
- `sqlite3`'s rows are `Any` in typeshed (`Row.__getitem__`, `fetchone`), and so is Starlette's `path_params`.
  `uv run mypy src/p2pwatch/adapters/driven/persistence_sqlite --disallow-any-expr` from `packages/crawler`: 166
  errors in 19 files.
- `sqlc-gen-python` types PostgreSQL only and its code depends on SQLAlchemy (its documentation, through Context7),
  so no generator checks our SQL statically.
- Keyword-only calls: `ruff check packages/*/src --preview --select PLR0917 --config
  "lint.pylint.max-positional-args=1"` reports 240 definitions in 111 files; 150 dataclasses have two fields or
  more, none `kw_only`.
