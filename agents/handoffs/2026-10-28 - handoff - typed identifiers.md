# Handoff: identifiers typed apart from bare strings

Drafted by block 100 from the lot's block reports (#533, #534, #536, #537, #538, #539, #540, #541, #542) and its own,
for the closing block 110 to correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-28-typed-identifiers.md` (reviewed by `typed-ids-spec-review`, approved by
the operator 2026-10-28). It ships the backlog entry "Identifiers typed apart from bare strings" (D2 of
`agents/specs/2026-10-09-stage2-search-download-status-ports.md`), widened to `FileId`, `SourceId`, `Uid` and `Gid`,
which the closing block deletes from `BACKLOG.md`, and adds two entries agreed by the operator (spec section 7):
"Rows read by column name" under Debt, "Keyword-only calls" under Technical improvements.

One stack cut from `main` at `ca871563`, which had not moved when block 100 was written (`git fetch`, 2026-10-28).
Eleven blocks. Before Act, block 10 of the first draft split into 10 and 20, and its block 70 into 80, 90 and 100.
Blocks 40 to 70 passed 20 files, block 50 also its estimate of 500 lines, under the mechanical exemption on their
spec rows (operator, 2026-10-28).

| Block | Pull request | Branch |
|---|---|---|
| 10 | #533 | `refactor/uid-gid-settings` |
| 20 | #534 | `refactor/uid-gid-ports` |
| 30 | #536 | `refactor/completed-download-without-target` |
| 40 | #537 | `refactor/target-id-type` |
| 50 | #538 | `refactor/node-id-type` |
| 60 | #539 | `refactor/client-name-and-channel-types` |
| 70 | #540 | `refactor/keyword-type` |
| 80 | #541 | `refactor/webui-hex-names` |
| 90 | #542 | `refactor/file-id-type` |
| 100 | #TBD | `refactor/source-id-type` |
| 110 | #TBD | `docs/typed-identifiers-wrap` |

Not merged at writing. **No release follows this lot**: the v5 waits for a P2P network other than eD2k (operator,
2026-10-27). Nothing the operator sees changes (spec section 2); the image changes only in its annotations and in
D6's notification text, so the lot reaches the node with the v5 release, or through a `main` image.

## What was built

- **The types** (D1, D3): each a `NewType` in its package's `domain/identifiers.py`. `p2pwatch`'s holds `NodeId`,
  `ClientName`, `Channel`, `Keyword` over `str` and `FileId`, `SourceId` over `bytes`; `catalog_matching`'s holds
  `TargetId`; `p2pwatch_amule`'s holds `Uid` and `Gid`. Each package's `tests/domain/test_identifiers.py` holds a
  call per type under `# type: ignore[arg-type]` with a bare literal, and one per pair of types of one raw type (the
  crawler pairs `TargetId` with its own `str` types), so mypy's `warn_unused_ignores` fails the gate if two types
  stop being told apart.
- **The conventions** (block 10): `AGENTS.md`'s Naming says an identifier is a `NewType` named after its variable in
  CamelCase, in its package's `domain/identifiers.py`, typed where it enters; `uid` and `gid` join the allowed
  abbreviations.
- **`Uid`, `Gid`** (blocks 10, 20, D10): `PUID` and `PGID` each through their own parser (`_puid`, `_pgid`) over one
  shared `_numeric_id(env, name) -> int`, so the error messages are unchanged; the four boot ports, their adapters,
  `change_owner`'s `Callable` and `FakeOwnership.chowns` carry them. `tach.toml`: the four ports and their adapters
  gain `p2pwatch_amule.domain`.
- **D6** (block 30): `DownloadTracker` dispatches `DownloadCompleted` with `target_titles == ()` when the labeler
  finds none, instead of a `TargetTitle("unknown", "")`; the policy's line still reads `✅ download completed:
  unknown`, and `AppriseNotifier`'s shared `_targets_section` writes `**Targets**\nunknown` (it wrote `unknown - `).
- **`TargetId`** (block 40): from `TargetSegment.target_id` through the crawler; the webui's `?target_id=` filter goes
  through a new `_normalize_target_id`, beside `_normalize_tier`; `SqliteDecisionStore.read_latest_decisions` keys its
  dictionary by each decision's `target_id`. `tach.toml` unchanged (a crawler import of `catalog_matching` crosses a
  distribution).
- **`NodeId`** (block 50): from `Uuid4NodeIdGenerator`, `SqliteNodeIdStore` and every reader returning an
  observation, a source point or a node state; `CrawlerLifecycle`'s loops take `Callable[[NodeId], ...]`.
  `tach.toml`: `node_id_generator`, `node_id_reader`, `node_id_writer` and `uuid4_node_id_generator` gain
  `p2pwatch.domain`. The fakes record `NodeId`s; the raw-row seeders of the tests keep `node_id: str`.
- **`ClientName`, `Channel`** (block 60): from the composition's `_AMULE_CLIENT_NAME`, the amuleapi adapter's
  `_SEARCH_TYPES` and status mapper, `SqliteBackoffStateStore` and `SqliteNodeStateReader`; `BackoffKey.channel` is
  `Channel | None`.
- **`Keyword`** (block 70, D5): `SearchKeyword` is gone; `dedupe_keywords` returns `Keyword`s, the config keeps
  `tuple[str, ...]`; the amuleapi adapter's `_keywords_without_kad_word` is a `set[Keyword]`, `_kad_next_start`'s keys
  stay `str` (appendix B).
- **D7** (block 80): the display field `file_id` is `file_id_hex`, the routes and their `path_params` keys
  `/files/{file_id_hex}` and `/sources/{source_id_hex}`; the URLs do not change. `AGENTS.md`'s WebUI row follows.
- **`FileId`** (block 90): `FileKey.file_id` returns one, carried by `CatalogFileReader`, `FileDescriber` and the
  webui's file page from the URL (`FileId(bytes.fromhex(...))`) to the SQL read; `variants.file_id`, the SQL function,
  returns one too.
- **`SourceId`** (block 100): `SourceKey.source_id` returns one, carried by `SourceReader.read_source_history`,
  `SourceDescriber` and the webui's source page from the URL (`SourceId(bytes.fromhex(...))`) to the SQL read.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1712 passed at block 100; 100 % branch coverage;
`_unit-coverage-check` clean).

Budgets against each parent: block 10, 64 lines and 7 files; block 20, 82 and 19; block 30, 24 and 7; block 40, 460
and 59 (exemption); block 50, 356 and 77 (exemption); block 60, 411 and 49 (exemption); block 70, 227 and 35
(exemption); block 80, 13 and 5; block 90, 40 and 15; block 100, 45 and 14.

Appendix C at block 100's tip (`0a5605bd`), each `git grep` with `packages/*/src` unquoted:

- 1: `mypy src tests` "Success" in `crawler` (17 ignores in its identifier test), `matching` (1) and `amule` (4).
- 3: the `str` command prints `persistence_sqlite/variants.py:25-26` (`keyword`, `node_id`) and nine lines of
  `webui/displays.py`, nothing else; the `bytes` and `int` commands print nothing.
- 4, 5, 6: print nothing.

Each type's identifier test watched failing, from the block reports: with the type a plain alias of its raw type
(`Uid = int`, `TargetId = str`, ...), mypy's `Unused "type: ignore" comment [unused-ignore]`, exit 1: 4 lines for
`Uid`, `Gid` (block 10), 1 for `TargetId` (40), 2 for `NodeId` (50), 4 for `ClientName`, `Channel` (60), 2 for
`Keyword` (70), 1 for `FileId` (90), 2 for `SourceId` (100, lines 60 and 95: the bare `bytes` and the `FileId`
passed as a `SourceId`). A line pairing a type with another already distinct stays used under the alias, so it proves
the pairing only once both are `NewType`s.

Other tests watched failing:

- Block 20: a temporary swap `set_amule_conf(conf, boot_settings.pgid, boot_settings.puid)` passed mypy before the
  ports changed, then failed after with `Argument 2 to "set_amule_conf" of "AmuleConfWriter" has incompatible type
  "Gid"; expected "Uid"`; reverted, not committed.
- Block 30 (criterion 2): `target_titles: (TargetTitle(target_id='unknown', title=''),) != ()`; `assert '✅
  download completed: ' == '✅ download c...eted: unknown'`; the notifier's body ending its targets section with
  `unknown - `.
- Block 70: `tests/domain/search/test_keywords.py`, 3 tests, `dedupe_keywords` still returning `SearchKeyword`s.
- Block 80 (a rename, no new test): the route renamed but `path_params["file_id"]` kept, `KeyError: 'file_id'`; the
  same for `source_id`, 20 failed; `files.html` reading `row.file_id`, `UndefinedError`, 29 failed.

## Departures from the spec

None declared by any block. Choices the spec left open:

- Block 10: D10's two parsers share `_numeric_id`, so the error messages stay as they were.
- Block 20: beyond the four ports, `change_owner`'s `Callable` and `FakeOwnership.chowns` carry `Uid`, `Gid` (D4).
- Block 40: `explanation_target_id` in the file page's handler stays `str | None`: it only feeds a display.
- Block 70: the tests of `SearchKeyword`'s equality and hashing went with it.
- Block 80: the test URL placeholders of `test_app.py` follow the route.
- Block 100: `test_source.py`'s check that a source's id never equals the file id of the same native id compares
  `bytes(source_id)` with the `FileId`, since `strict-equality` refuses `==` between the two types.
- Blocks 60, 70, 90, 100: a test's expected dictionary or list with unwrapped keys or values (`{"amuled": None}`
  against a `Mapping[ClientName, ...]`, `client.searches == [("keroro", "ed2k")]`, a fake's recorded call
  `{"source_id": b"\x01" * 16}`) passes mypy and was left unwrapped, D9 being applied to the literals passed where a
  type is expected.

## Class 1 fixes

None in the lot. No class 2 question.

## The holistic review

To be written by block 110.

## Counts

No fix-back and no cascaded rebase up to block 100. No body called unreadable so far.

## Pitfalls

- `git grep` with a quoted `'packages/*/src'` pathspec prints nothing: the spec's commands rely on the shell
  expanding it unquoted (block 40).
- A comparison between a `NewType` over `str` and a `str` literal (`== "062A"`) stays legal under `strict-equality`,
  and so does a dictionary of unwrapped keys compared to a `Mapping[ClientName, ...]` (blocks 40, 60): neither is
  evidence that a test wraps its literals. Between two `NewType`s, `==` is refused.
- A `NewType(...)` call in a parameter default is refused by ruff's B008: hoist it to a module constant (blocks 40,
  50).
- pytest's `parametrize` values are not checked against the parameter's annotation: wrap them by hand (block 70).
- A nullable column needs an explicit wrap, `None if channel is None else Channel(channel)` (block 60).
- Serena renames neither a template's attribute nor the constructor keyword feeding it (block 80, the `AGENTS.md`
  gotcha).
- `mypy` on a lone test file of `p2pwatch_amule` from its package directory fails on missing imports; run
  `mypy src tests` as `type-check` does (block 100).
- `uv run poe fix` reports a pre-existing sqlfluff parsing error under `packages/crawler/src` and its `lint-fix` step
  exits non-zero; `poe check`'s `sql-lint` is green (block 10). Not fixed in this lot.

## Not validated

- A wrap from an untyped source (an SQLite row, a URL parameter) is unchecked by mypy (spec section 7): a reader that
  wraps the wrong column passes. The Debt entry "Rows read by column name" carries it.
- D6's log line and notification on a real node: the case does not occur in normal operation.
- The integration suites run only in CI's `validate / gate`.

## Next

No release proposal: the v5 waits for a P2P network other than eD2k. Then `BACKLOG.md`, read before proposing.
