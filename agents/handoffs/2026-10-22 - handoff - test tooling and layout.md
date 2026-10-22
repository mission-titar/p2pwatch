# Handoff: the test tooling and the layout, lot A of the post-hexagonal corrections

Drafted by block 72 from the lot's block reports (#389, #390, #392 to #405) and its own; to be corrected by the
closing block 90 with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-22-test-tooling-and-layout.md` (approved 2026-10-22, with the exemptions
of blocks 30, 50, 52 and 70). It applies the ledger `agents/reference/2026-10-22-post-hexagonal-audit.md`'s rows H8,
H9, A16, R1, R4 (the pure modules' move only), R9, R10, R12 (item 3), R13, R14, R15 and D6, and revises H8 and A16
(D5). Lots B (the names, the other hexagons' fixes) and C (the crawler's design fixes) follow, each with its own
Discuss and spec.

One stack cut from `main` at `d4180cdf`. Eighteen blocks: the spec's rows 10 to 72, row 66 split in Act into 66 and
68 at the line bound, then the closing block 90.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #389 | `chore/pyrefly-in-gate` |
| 20 | #390 | `chore/pytest-settings-plugin` |
| 22 | #392 | `chore/pytest-settings-applied` |
| 30 | #393 | `refactor/fold-crawler-testing` |
| 32 | #394 | `test/fakes-and-support-covered` |
| 40 | #395 | `refactor/fakes-one-per-port` |
| 42 | #396 | `refactor/inline-fakes-deduplicated` |
| 50 | #397 | `refactor/one-port-per-file` |
| 52 | #398 | `refactor/application-rings` |
| 54 | #399 | `chore/ring-rules` |
| 60 | #400 | `refactor/crawler-composition` |
| 62 | #401 | `refactor/amule-composition` |
| 64 | #402 | `refactor/vex-template-composition` |
| 66 | #403 | `refactor/bump-coverage-composition` |
| 68 | #404 | `refactor/coverage-composition` |
| 70 | #405 | `refactor/fakes-in-their-ring` |
| 72 | to fill | `test/fakes-layout` |
| 90 | to fill | `docs/test-tooling-and-layout-wrap` |

Nothing of the stack is merged. The lot changes no image (Acceptance 9), so it releases nothing; "A copy before a
migration that rewrites rows" still ships before the next release.

## What was built

- **pyrefly in the gate** (block 10): `[tool.pyrefly]` in every package (`search-path = ["src", "."]`, import
  errors only), `pyrefly-check` in `lint-all`, pyrefly 1.4.0 a dev dependency (Serena's version).
- **`pytest_settings`** (blocks 20, 22): a ninth workspace member, one module auto-loaded through its `pytest11`
  entry point, turning `PytestUnknownMarkWarning`, `ResourceWarning` and `PytestUnraisableExceptionWarning` into
  errors in every package's run, the gate's or a hand-run one; the packages' own `--strict-markers` and filters gone.
  Outside vulture's scope, declared in `tach.toml` with no ring (C6).
- **`p2pwatch_testing` folded** into the crawler's `tests/fakes/` and `tests/support/` (block 30), the package and
  its configuration removed; every package measures `tests`, test files and conftests omitted (blocks 30, 32, C5).
- **One fake per port** (blocks 40, 42): `FakeCatalogReader`, `FakeDownloadClient`'s `SourceClient` half and
  `FakeCrawlControls` split; the duplicated inline doubles made one (`FakeSourceReader`, `FakeCatalogFileReader`,
  `FakePolicyFingerprintStore`, `FakeShutdownRequester`, `FakeWaker`).
- **One port per file** (block 50), the port errors in `domain/` (`client_errors.py`, `repository_errors.py`,
  `catalog_copy_error.py`, `merge_error.py`); checked by `packages/crawler/tests/test_port_files.py` (block 54, C2).
- **The rings of `application/`** (blocks 52, 54): `application/ports/{driving,driven}/`, `use_cases/`, `steps/`,
  the lifecycles (`CrawlerLifecycle`, `PortSyncLifecycle` and its `run`); `edge_state`, `matching_read`,
  `source_alerts` in `domain/`; `CrawlerComposition`, `PortSyncComposition`. tach's layers `composition`,
  `adapters`, `lifecycle`, `steps`, `use_cases`, `ports`, `domain`, `use_cases`' visibility refusing a step's
  import (C1).
- **Every hexagon's wiring in `composition/`** (blocks 60 to 68): `composition/command_line.py`'s
  `build_command_line(...)` in all six, `__main__.py` reading the process state only; `amule_bump`'s
  `build_amule_bumper` as the seam its tests tune; `UnitCoverageComposition` implements `UnitCoverageChecker` to
  hold coverage.py's `TemporaryDirectory()` for one call (C3, reworded by the operator).
- **Each double in its file, in its ring** (blocks 70, 72): `tests/fakes/{adapters/driven,application/use_cases,
  composition}/` and the root for outside systems, one double per file named after it; checked by
  `packages/crawler/tests/test_fake_files.py` (C4).
- **`AGENTS.md`**: C1 (rings, glossary `ring`, `use case`, `step`, `lifecycle`), C2, C3, C4 (Hard rules, Naming's
  store fake, glossary `store`), C5, C6.

## What an operator sees change

Nothing: no config key, schema, route, metric, notification or image changes. Contributors see `poe
pyrefly-check`, the plugin's three errors in a hand-run `pytest`, and the new paths of ports, use cases and doubles.
The logger names written as literals keep their text although their modules moved (lot B's R8).

## Acceptance

Re-run by block 72 on 2026-10-22 at its commit unless noted.

1. Block 10: an injected `from tests.fakes.nowhere import X` fails `poe pyrefly-check` in each of the 8 packages
   (`[missing-import]`); the tree passes.
2. Blocks 20, 22: an injected `@pytest.mark.misspeled` test gives `1 error`, an injected `sqlite3.connect(":memory:")`
   then `gc.collect()` `1 failed`, hand-run in all seven packages with tests.
3. Blocks 30, 32: an injected unused method in a fake fails the gate in all six packages with doubles, and an
   unused function in the crawler's `tests/support/` (`99.97%`).
4. `find packages -path '*/src/*' -type d -name ports -not -path '*/application/*'` prints nothing. Block 54: tach
   refuses a use case importing a step and a step importing the lifecycle (`Layer ... is lower than layer ...`; the
   second first as a circular dependency), and a step importing a use case (`does not match its visibility`).
5. Block 54: an injected `class ExtraPort(ABC)` and a port file renamed away from its class each fail
   `test_port_files.py`.
6. Every `__main__.py` imports the standard library and its `composition.command_line` only; all six
   `composition/command_line.py` exist.
7. Block 72: `test_fake_files.py` fails on a copy of `FakeVexReader` under `application/use_cases/` (expected
   `adapters/driven`), on `FakeUnitCoverageChecker` at the root (expected `composition`), on a second class
   `FakeExtra` in `fake_ownership.py`, and on `FakeSourceReader` also inheriting `DecisionReader`; each reported by
   its own test.
8. **Not measured.** Block 10's live Serena reached `RepoReader.read_file` in full and `VexReader.read_claims` on its
   port's line only, from a pyrefly server started before the configuration changed; a fresh `pyrefly lsp` reached
   every site on this branch and on `main`'s configuration alike, so it does not reproduce the trial's baseline. To
   measure with a fresh Serena on a clone, on `main` and at the top.
9. `git diff --stat d4180cdf HEAD` over `deploy`, `security`, the crawler's `migrations`, `packages/amule/docker`,
   both Dockerfiles and `.github/workflows` prints nothing.
10. The gate green at every block (each report); CI green on every block's head up to 70 at writing.

## Holistic review

To be written by the closing block from `.reviews/lot-a-holistic.md`.

## Departures from the spec

- Block 10: `AGENTS.md`'s gotcha kept its rule with its remaining reason; block 30 moved it into the tests
  paragraph of "The gate is PER PACKAGE".
- Block 20: the VEX source rules ignore `packages/pytest_settings/src/**`; a fourth test (a package's own filter does
  not lift the shared one); the inner runs pass `-p no:asyncio`.
- Block 30: the three modules of doubles kept their relative paths until block 70; class 1 fixes in
  `docs/contributing/architecture.md` and `testing.md`.
- Block 32: C5 named `tests/fakes/` while five packages still had a `tests/fakes.py` module until block 70.
- Block 42: `_NoSetStateStore` stayed in its test module until block 70; the fingerprint store's argument is
  `stored_fingerprint`, `FakeWaker`'s new record `waited_subjects`.
- Block 50: `CatalogCopyError` and `MergeError` in `catalog_copy_error.py` and `merge_error.py`.
- Block 52: the compositions' files renamed after their classes (`crawler_composition.py`,
  `port_sync_composition.py`).
- Block 54: `docs/contributing/architecture.md` given the rings; `steps/supervise_loops.py` named as the exception
  until lot C.
- Block 66: split at the line bound (574 lines), `coverage_checks` and C3 as block 68; `build_amule_bumper` the seam
  a test tunes.
- Block 68: C3 reworded by the operator ("the composition builds each graph when what it needs exists"), one
  fix-back.
- Block 70: `_Const` (matching) and `_BlockedLoop` (crawler) stay in their test modules (operator); a moved private
  double loses its underscore and nothing else.
- Block 72: C4 corrected in the spec (the boundary's doubles; one double per file, not one `Fake*` class). Where
  both a use case and the composition implement a driving port (`UnitCoverageChecker`), the double sits in the
  outermost ring, the composition: it replaces what the code under test is handed. `snake_case` moved from
  `test_port_files.py` to `tests/support/snake_case.py`, shared by both layout tests. `docs/contributing/testing.md`
  says every double lives in `tests/fakes`, one per file.

## Names settled by teammates

`pytest_settings`'s hook, `catalog_copy_error.py`, `merge_error.py`, `crawler_composition.py`,
`port_sync_composition.py`, `build_amule_bumper`, `UnitCoverageComposition`, `FakePolicyFingerprintStore`,
`stored_fingerprint`, `waited_subjects`, `FakeCrawlerRunner` (was `_FakeCrawlerRunner`), `test_fake_files.py`,
`snake_case`.

## For lot B and the holistic review

- **The doubles' names (N10)**: 21 doubles lack the `Fake` prefix (`BlockingMonotonicClock`, `HangingNotifier`,
  `ImmediateLoop`, `LaggingDownloadStore`, `NeverSuspends`, `NoSetStateStore`, `NotificationSink`, `RaisingNotifier`,
  `RecordingLoop`, `RecordingNotifier`, `RecordingStatusWriter`, `SavesRecorded`, `ScriptedClient`, `ShutDownServer`,
  `ShutdownDuringCycleCatalog`, `SteppedClient`, `ThreadRecordingContext`, `TickingMonotonicClock`,
  `TickingWallClock`, `TimedClient`, `TimedEventEmitter`), and three Writer/Reader fakes are not named
  `Fake<Thing>Store` (`FakeRunState`, `FakeAmuleConf`, `FakeDockerfile`). Each rename moves its file, since the
  file is named after the class.
- **The literal logger names** no longer match their moved modules (R8); `AGENTS.md` and
  `docs/contributing/architecture.md` still say a use case logs "under the module's name".
- **`vex_checks`' root from `__file__`** in `__main__`, checked only by CI's `poe vex-claim-coverage` (H3).
- **`_Controls`**, the webui tests' local holder joining the three control fakes' calls (block 40), for the holistic
  review.
- **`SavesRecorded`** subclasses the real `SqliteBackoffStateRepository` (a spy on an adapter, not a fake of its
  ports); the layout test places it by the ports it inherits.
- **The layout test's reach**: it follows bases written as a bare name or a `Name[...]` imported by `from x import`,
  not `module.Port`; a record is a dataclass with no base.

## Pitfalls

- **Serena's first `rename_symbol` after start can apply its edits at shifted offsets** (block 52, as the bench
  says): revert and run it again, then check the diff.
- **Serena's references missed a use through a module constant** (block 40): a split replacing one object with
  several needs mypy, not only the tests.
- **A same-size edit undone within the second leaves a stale `.pyc`** (block 54): clear `tests/__pycache__` after a
  mutation check.
- **`-p no:tach` makes pytester's inner runs panic** (`pyo3_runtime`, block 20).
- **A test helper running a nested `Coverage` cannot sit in `tests/support/`** (block 68): the inner tracer hides its
  lines from the package's measure (58 %).
- **pyrefly with no `[tool.pyrefly]` in a package** falls back to the root's and checks the whole workspace (block
  10).
- **tach declares no dependency across distributions** (blocks 50, 54): `catalog_matching` from `p2pwatch` is
  `check-external`'s.
- **zsh does not split an unquoted `$files` on newlines** (block 30): `git grep -lz | xargs -0`. `git add` with one
  missing pathspec stages nothing.
- **A cut of a module that joins its kept statements loses their spacing** (block 70): keep the original text with
  the moved ranges deleted; a `type` alias statement is not an `Assign`.
- **Host port 4711 is the deployed node's**: never publish it, never touch the `mulewatch-*` containers.

## Not validated

- Acceptance 8 (above).
- The integration suites locally; CI runs them on both architectures.
- CI on blocks 72 and 90 at writing.

## Wrap counts

From `gh run list --branch <branch>` over blocks 10 to 70 on 2026-10-22, at writing.

- **Runs**: 19 for 16 blocks. Block 68 has two green runs (its fix-back, C3's wording). Block 70 has one green run
  and two cancelled (`31a49f3d`, and a first run of `2ed0a0c5`).
- **Fix-backs**: 1 (block 68). **Cascaded rebases**: to count. **Runs they re-triggered**: to count.
- **Splits**: 1 (block 66 at the line bound). **Exemptions**: 4 (blocks 30, 50, 52, 70), approved on their rows.
- **Bodies called unreadable**: none at writing.

## Next

- The holistic review over the stack, then the closing block 90.
- The operator reviews and merges the stack, after the lead rebases it onto `main` if `main` moved.
- Lot B's Discuss and spec: the names (R3, R5, R8, N1 to N18, N10 above) and the other hexagons' fixes (H1 to H7,
  H10 to H15, R6 and R11 outside the crawler).
