# Handoff: identifiers typed apart from bare strings

Drafted by block 100 from the lot's block reports (#533, #534, #536 to #542) and its own, corrected by the closing
block 130 with the holistic review and the reports of blocks 110 and 120 (#544, #545).

## State

Tier Spec lot. Spec `agents/specs/2026-10-28-typed-identifiers.md` (reviewed by `typed-ids-spec-review`, approved by
the operator 2026-10-28). It ships the backlog entry "Identifiers typed apart from bare strings" (D2 of
`agents/specs/2026-10-09-stage2-search-download-status-ports.md`), widened to `FileId`, `SourceId`, `Uid` and `Gid`,
which the closing block deletes from `BACKLOG.md`, and adds two entries agreed by the operator (spec section 7):
"Rows read by column name" under Debt, "Keyword-only calls" under Technical improvements.

One stack cut from `main` at `ca871563`, which had not moved when block 130 was written (`git fetch`, 2026-10-28).
Thirteen blocks against the spec's eleven. Before Act, block 10 of the first draft split into 10 and 20, and its block
70 into 80, 90 and 100. After the holistic review, the lead cut blocks 110 and 120 from its findings, so they are not
in the spec's table, and the closing block, numbered 110 there, became 130. Blocks 40 to 70 passed 20 files, block 50
also its estimate of 500 lines, under the mechanical exemption on their spec rows (operator, 2026-10-28); block 120
passed 20 files under the same exemption, asked of the operator after the block, not before (Pitfalls).

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
| 100 | #543 | `refactor/source-id-type` |
| 110 | #544 | `refactor/holistic-findings` |
| 120 | #545 | `test/node-id-constant-names` |
| 130 | this block's pull request | `docs/typed-identifiers-wrap` |

Not merged at writing. **No release follows this lot**: the v5 waits for a P2P network other than eD2k (operator,
2026-10-27). Nothing the operator sees changes (spec section 2); the image changes only in its annotations and in
D6's notification text, so the lot reaches the node with the v5 release, or through a `main` image.

## What was built

- **The types** (D1, D3): each a `NewType` in its package's `domain/identifiers.py`, whose three docstrings say the
  same thing (block 110). `p2pwatch`'s holds `NodeId`, `ClientName`, `Channel`, `Keyword` over `str` and `FileId`,
  `SourceId` over `bytes`; `catalog_matching`'s holds `TargetId`; `p2pwatch_amule`'s holds `Uid` and `Gid`. Each
  package's `tests/domain/test_identifiers.py` holds a call per type under `# type: ignore[arg-type]` with a bare
  literal, and one per pair of types of one raw type (the crawler pairs `TargetId` with its own `str` types: ten
  pairs, four of them added by block 110), so mypy's `warn_unused_ignores` fails the gate if two types stop being
  told apart.
- **The conventions** (block 10): `AGENTS.md`'s Naming says an identifier is a `NewType` named after its variable in
  CamelCase, in its package's `domain/identifiers.py`, typed where it enters; `uid` and `gid` join the allowed
  abbreviations.
- **`Uid`, `Gid`** (blocks 10, 20, 110, D10): `PUID` and `PGID` each through their own parser (`_puid`, `_pgid`) over
  one shared `_numeric_id(env, name) -> int`, so the error messages are unchanged; the settings' fields are `uid` and
  `gid` (block 110), as the four boot ports, their adapters, `change_owner`'s `Callable` and `FakeOwnership.chowns`
  name them. The parsers keep the external names they read. `tach.toml`: the four ports and their adapters gain
  `p2pwatch_amule.domain`.
- **D6** (block 30): `DownloadTracker` dispatches `DownloadCompleted` with `target_titles == ()` when the labeler
  finds none, instead of a `TargetTitle("unknown", "")`; the policy's line still reads `✅ download completed:
  unknown`, and `AppriseNotifier`'s shared `_targets_section` writes `**Targets**\nunknown` (it wrote `unknown - `).
- **`TargetId`** (blocks 40, 110): from `TargetSegment.target_id` through the crawler; the matching engine's winner
  key `best_key` is a `tuple[int, int, TargetId]` (block 110); the webui's `?target_id=` filter goes through a new
  `_normalize_target_id`, beside `_normalize_tier`; `SqliteDecisionStore.read_latest_decisions` keys its dictionary
  by each decision's `target_id`. `tach.toml` unchanged (a crawler import of `catalog_matching` crosses a
  distribution).
- **`NodeId`** (blocks 50, 120): from `Uuid4NodeIdGenerator`, `SqliteNodeIdStore` and every reader returning an
  observation, a source point or a node state; `CrawlerLifecycle`'s loops take `Callable[[NodeId], ...]`.
  `tach.toml`: `node_id_generator`, `node_id_reader`, `node_id_writer` and `uuid4_node_id_generator` gain
  `p2pwatch.domain`. The fakes record `NodeId`s; the raw-row seeders of the tests keep `node_id: str`. The tests'
  module constants holding one are `_NODE_ID` (`NODE_ID` in `tests/support/application/steps/download_cycle.py`),
  19 of them renamed from `_NODE` (block 120).
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
- **`BACKLOG.md`** (block 130): the shipped entry deleted, the two entries of spec section 7 added verbatim.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1712 passed at block 100, 1716 at blocks 110 to 130;
100 % branch coverage; `_unit-coverage-check` clean).

Budgets against each parent: block 10, 64 lines and 7 files; block 20, 82 and 19; block 30, 24 and 7; block 40, 460
and 59 (exemption); block 50, 356 and 77 (exemption); block 60, 411 and 49 (exemption); block 70, 227 and 35
(exemption); block 80, 13 and 5; block 90, 40 and 15; block 100, 45 and 14; block 110, 54 and 11; block 120, 296 and
24 (exemption); block 130, 7 and 1 (`BACKLOG.md`; the handoff is outside the count).

Continuous integration, `gh pr checks <n> --required` (2026-10-28): `validate / gate` passes on #533, #534 and #536
to #545, each on its first run but #537's. #537's first run (40774390912) failed in `build-and-verify (arm64)` on a buildx infrastructure error, `error
writing layer blob: not_found`; `gh run rerun 40774390912 --failed` passed (attempt 2). The lead first reported #537
green, its watch command ending with an `echo` whose exit is always 0.

Appendix C, re-run at block 120's tip (`4e5234ac`), each `git grep` with `packages/*/src` unquoted:

- 1: `mypy src tests` "Success" in `crawler` (25 ignores in its identifier test: 6 for the bare literals, 19 for
  the 11 pairs, each both ways but `TargetId`'s with `ClientName`, `Channel` and `Keyword`), `matching` (1) and `amule` (4).
- 3: the `str` command prints `persistence_sqlite/variants.py` (2 lines: `keyword`, `node_id`) and nine lines of
  `webui/displays.py`, nothing else; the `bytes` and `int` commands print nothing.
- 4, 5, 6: print nothing.

Each type's identifier test watched failing, from the block reports: with the type a plain alias of its raw type
(`Uid = int`, `TargetId = str`, ...), mypy's `Unused "type: ignore" comment [unused-ignore]`, exit 1: 4 lines for
`Uid`, `Gid` (block 10), 1 for `TargetId` (40), 2 for `NodeId` (50), 4 for `ClientName`, `Channel` (60), 2 for
`Keyword` (70), 1 for `FileId` (90), 2 for `SourceId` (100, lines 60 and 95: the bare `bytes` and the `FileId`
passed as a `SourceId`). A line pairing a type with another already distinct stays used under the alias, so it proves
the pairing only once both are `NewType`s. Block 110's four new pairs, each watched failing with
`uv run mypy --no-incremental tests/domain/test_identifiers.py` under one mutation of `identifiers.py`: `ClientName =
NodeId`, `Channel = NodeId`, `Keyword = NodeId`, `Keyword = ClientName`, each 2 unused ignores (lines 100 to 119);
the control, the parent's test file under `ClientName = NodeId`, "Success".

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
- Blocks 110 (the `uid`/`gid` rename, `best_key`, the docstrings) and 120 (the constants' rename): no new behaviour,
  so no test watched failing; the gate's mypy run covers the renames. After block 120, `git grep -nwE "_NODE|NODE"
  packages/crawler/tests` prints nothing.

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
- Blocks 110, 120, 130: not in the spec's table (State).

## Class 1 fixes

None in the lot. No class 2 question.

## The holistic review

By `typed-ids-holistic-review` over `git diff origin/main...origin/refactor/source-id-type` (blocks 10 to 100):
CRITICAL 0, MAJOR 0, MINOR 8. Spec conformance clean: criteria 1 to 6, the conventions, section 6's documents, D1's
`(Corrected: ...)`; no runtime behaviour moves but D6's.

| Finding | Exit |
|---|---|
| The crawler's identifier test missed four of its ten `str` pairs (`NodeId`/`ClientName`, `NodeId`/`Channel`, `NodeId`/`Keyword`, `ClientName`/`Keyword`), so `ClientName = NodeId` passed the gate | fixed, block 110: the four pairs, each watched failing |
| The settings' fields `puid`/`pgid` broke "one concept, one name": the ports say `uid`/`gid` | fixed, block 110: `BootSettings` and `PortSyncSettings` say `uid`/`gid`; the parsers `_puid`/`_pgid` keep the external names they read |
| `_NODE` constants holding a `NodeId`, and `NodeId("n1")` literals repeated across modules instead of in `tests/support/` | fixed, block 120: 19 constants renamed `_NODE_ID` / `NODE_ID`; the literals' half accepted, each module's node id serving that module alone |
| `engine.py`'s `best_key` typed its target id `str` | fixed, block 110: `tuple[int, int, TargetId] \| None` |
| The three `identifiers.py` docstrings disagreed ("reads", "produces") | fixed, block 110: all three say "carries" |
| #533, #534 and #542 lacked the closing attribution lines | fixed by the lead with `gh pr edit` |
| #537's `validate / gate` red on an arm64 buildx error | fixed, `gh run rerun 40774390912 --failed`, green on attempt 2 |
| The handoff draft: `#TBD` for block 100, "one per pair" untrue, no CI result | fixed, block 130: this document |

## Counts

No fix-back and no cascaded rebase so far. One CI rerun, #537's, for an infrastructure failure. 13 blocks against 11
planned. No body called unreadable so far.

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
- mypy's incremental cache missed an edit of `identifiers.py` that kept the file's size (`Channel = NodeId`, then
  `Keyword = NodeId`) and reported the previous run's errors: run a mutation trial with `--no-incremental` (block 110).
- Serena's renames of `BootSettings.puid`/`pgid`, run back to back, wrote the second at shifted offsets in
  `boot_container.py`, missed `port_sync_lifecycle.py` for `PortSyncSettings`, and renamed no dataclass keyword: the
  edits were discarded and the rename done by anchored `sed`, its diff read line by line (block 110).
- A mechanical rename past 20 files (block 120: 296 lines, 24 files, 5 of them through the support module's `NODE`)
  takes the exemption, which the lead asks of the operator before the block starts; here it was asked after.
- Under zsh, `sed -i ... $files` does not word-split a variable: pipe `git grep -lz` into `xargs -0` (block 120).
- A watch command ending with `; echo ...` exits 0 whatever the run's result: read `gh run watch --exit-status`'s own
  exit, or `gh pr checks --required` (the lead, #537).

## Not validated

- A wrap from an untyped source (an SQLite row, a URL parameter) is unchecked by mypy (spec section 7): a reader that
  wraps the wrong column passes. The Debt entry "Rows read by column name" carries it.
- D6's log line and notification on a real node: the case does not occur in normal operation.
- The integration suites run only in CI's `validate / gate`.

## Next

No release proposal: the v5 waits for a P2P network other than eD2k. Then `BACKLOG.md`, read before proposing.
