# Post-hexagonal corrections, lot A: the test tooling and the layout

- Date: 2026-10-22. Status: approved by the operator on 2026-10-22, after Discuss and a review (`.reviews/lot-a-spec.md`: 0 critical, 12 major, 11
  minor, all answered here), with the exemptions of blocks 30, 50, 52 and 70.
- Tier: Spec. Origin: the ledger `agents/reference/2026-10-22-post-hexagonal-audit.md`, whose decisions this lot
  applies without restating them; it fixes rows H8, H9, A16, R1, R4 (the pure modules' move only), R9, R10,
  R12 (item 3), R13, R14, R15 and D6, and revises H8 and A16 (D5).
- **The ledger's code rows are cut into three lots** that merge one after the other: A, this one (test tooling, then
  the layout); B, the names (R3, R5, R8, N1 to N18) and the other hexagons' fixes (H1 to H7, H10 to H15, R6 and R11
  outside the crawler); C, the crawler's design fixes (A1 to A15, A17, R6, R6b, R6c, R7, R11 for the crawler). Why:
  measured at about 67 blocks as one lot, then regrouped with the mechanical exemption into about 17, 12 and 16 blocks
  with their closing ones (appendix); the order puts the moves before the renames, and both before the design fixes,
  so that a design fix lands in its final place under its final name. Each later lot has its own Discuss and spec;
  the ledger stays the checklist until a spec holds every row.
- What an operator sees change: nothing. No config key, schema, route, metric, notification or image changes; the
  logger names written as literals (`StdlibLogger("p2pwatch.application.search_worker")`,
  `getLogger("p2pwatch.composition.app")`, ...) keep their text although their modules move, until lot B derives
  them from the code (R8). No module logs under `__name__` today, so no log name moves with its module.
- Paths are under `packages/<pkg>/src/<module>/` unless noted.

## Summary

- **Every package's tests share one pytest configuration and one place for doubles**: a `pytest_settings` plugin,
  `tests/fakes/` for the doubles, `tests/support/` for the helpers, both measured at 100 %. `p2pwatch_testing` folds
  into the crawler's `tests/`.
- **pyrefly checks the imports in the gate**, so a rename from a port reaches every fake (H8's trial).
- **`application/` holds the ports, the use cases, the steps and the lifecycle**, in every hexagon; one port per
  file; every hexagon's wiring in `composition/`, `__main__.py` only reading the process state.

## Conventions this lot sets

Each goes into `AGENTS.md` in the block where the whole tree first follows it, so a rule never describes a tree that
does not follow it yet.

- **C1. `application/` holds `ports/{driving,driven}/`, `use_cases/`, `steps/` and at most one `<x>_lifecycle.py`.**
  A use case is called from outside, through a driving port, with the modules only it calls; a step is a stage of the
  lifecycle's graph, called only by the lifecycle or another step; the lifecycle is the program from its start to its
  stop, which the composition runs (`CrawlerLifecycle`, `PortSyncLifecycle`). Code that calls no port goes to
  `domain/`. tach: the lifecycle may import `steps/`; `use_cases/` and `steps/` never import each other nor the
  lifecycle. `AGENTS.md`'s rings and glossary (`lifecycle`, `step`, `use case`), block 54.
- **C2. One port per file, named after it** in snake case; the error types of ports, which both sides use, live in
  `domain/`. A test checks it. Hard rules, block 54.
- **C3. The composition**: every hexagon's `composition/command_line.py` exposes `build_command_line(...)`, which
  builds the adapters, the use cases and the command line, the fixed values (an address, a path, an executable, a
  URL, a width) being its constants; `__main__.py` reads the process state (argv, env, cwd, the root logger, the
  temporary directory) and calls `build_command_line(...).run(argv)`. The composition builds each graph when what it
  needs exists: at start, in `build_command_line`; during a call, by implementing the driving port that makes that
  call (`CrawlerComposition`, `PortSyncComposition`, `UnitCoverageComposition`). (Corrected: from "where the graph a
  driving port runs depends on what the command line has just read, the composition implements that port", which
  missed `UnitCoverageComposition`, holding coverage.py's `TemporaryDirectory()` for one check.) Hard rules, block 68
  (Corrected: from 66, split at the line bound).
- **C4. Doubles**: one fake per port, except a `<Thing>Writer` and `<Thing>Reader` pair, which share one
  `Fake<Thing>Store`. C4 governs the doubles of the hexagon's boundary (a port's implementation, an outside system,
  a callable an adapter receives); a stand-in for core code that one test module uses stays in it, like a harness
  (`_Const`, a domain `Matcher`). A fake is an adapter for tests, in the ring of what it replaces, one double per
  file, the file named after it: a driven port's fake, or the double of a callable an adapter receives
  (`FakeCommandRunner`), under `tests/fakes/adapters/driven/`; a driving port's fake under
  `tests/fakes/application/use_cases/`, or `tests/fakes/composition/` where the composition implements the port
  (`FakeCrawlerRunner`, `FakePortSyncLoopRunner`); a double of an outside system (`FakeAmuleApiServer`) at
  `tests/fakes/`'s root. A record a fake returns or keeps (`LoggedLine`, `WrittenSarif`) lives in its fake's file.
  `tests/support/` holds what is no double, at the mirror of the module it serves. A test checks the doubles' layout,
  not the `Fake` prefix, which lot B gives the doubles that lack it (N10). (Corrected: from "one `Fake*` class per
  file", without the boundary's scope; both decided by the operator in block 70.) Hard rules, Naming and the
  glossary (`store`), block 72.
- **C5. `tests/fakes/` and `tests/support/` are measured at 100 %** in every package, and left out of
  `_unit-coverage-check`; neither holds a file named `test_*.py`. Hard rules, block 32.
- **C6. `pytest_settings` is shared test configuration, not a hexagon**: one module, declared in `tach.toml`, holding
  what every package's pytest run applies, outside vulture's scope like the tests. Package boundary, block 20.

## Decisions

- **D1. pyrefly joins the gate, on import errors only.** Each package gets its `[tool.pyrefly]`
  (`python-interpreter-path = "../../.venv/bin/python"`, `search-path = ["src", "."]`, in this order), and a poe task
  `pyrefly-check` in `lint-all` runs `pyrefly check` in each. Why: H8's trial showed that only this section lets a
  rename from a port reach a fake's override in `tests/` (`RepoReader.read_file` 12 of 12 sites against 9), and that
  pyrefly's sub-configs cannot change import paths, so the section is per package; the check makes a forgotten
  section fail instead of silently shrinking the next rename. Import errors only, since mypy stays the type checker:
  `preset = "off"` and a `[tool.pyrefly.errors]` table setting `missing-import` and `missing-module-attribute` to
  `error` (prototype: a misspelled `from tests.fakes import X` fails, a type error passes; the eight packages pass
  as they are, so `amule_bump`'s `missing-attribute` needs no fix). pyrefly is pinned to Serena's version (1.4.0).
  `AGENTS.md`'s gotcha "a double two test modules share lives in `p2pwatch_testing`" loses its reason here (block 10)
  and its place at block 30.
- **D2. A `pytest_settings` plugin turns three warnings into errors** in every package (`PytestUnknownMarkWarning`,
  `ResourceWarning`, `PytestUnraisableExceptionWarning`), auto-loaded through its `pytest11` entry point, its
  `pytest_configure` appending them to `filterwarnings`; the packages' own `--strict-markers` and filters go. The
  first stands for `--strict-markers`: pytest 9.1 reads its command line and ini overrides before it loads a
  `pytest11` plugin, so a plugin cannot set the option, and an unknown marker becomes a collection error all the same
  (prototype, in the seven packages). Why: today `--strict-markers` is in three packages (the crawler, amule,
  matching; the ledger's H9 says two) and the filters in the crawler only, though amule and `amule_bump` run loopback
  servers; a plugin applies them to a hand-run `pytest` as to the gate's (a workspace test and poe's
  `PYTEST_ADDOPTS` were refused in the audit, H9). A module, not a hexagon (C6): it holds test configuration, as
  `conftest.py` or `[tool.pytest]` do, and no application; so vulture, which never reads the tests, does not read it
  either, where it would report the hook pytest calls by name. Its code is covered like any package's: its own run
  disables the auto-loaded copy (`-p no:settings`) and loads it from `conftest.py` once pytest-cov has started, since
  an entry-point plugin is imported before coverage starts. It has its own `[tool.pyrefly]` (D1). The prototype ran
  every suite with the filters on: no test fails.
- **D3. `p2pwatch_testing` folds into the crawler's `tests/`**, the package and its configuration removed, in one
  block. Its three modules of doubles go to `tests/fakes/` as they are (`application/fakes.py`,
  `application/download_fakes.py`, `adapters/mule_api/api_fakes.py`), split one per fake at block 70; its helpers
  to `tests/support/`: `catalog_rows` and `virtual_time` at its root, the SQLite helpers under
  `adapters/driven/persistence_sqlite/`. The crawler's `--cov=p2pwatch_testing` becomes the measure of D4 in the same
  block, so its doubles are never unmeasured. Why: the package exists only so that the crawler's tests share doubles,
  which `tests/fakes/` now does in every package alike (H8). The removal is no move, and the operator approves its
  exemption on its row: the workspace member, the crawler's `dev` dependency, the root's `[tool.uv.sources]`, ruff,
  TID251, deptry and mypy lines, `test_workspace_dependencies.py`'s edges, the ast-grep rules' ignores and rule test,
  the VEX source rules' paths and `AGENTS.md`'s sentences naming it.
- **D4. `tests/fakes/` and `tests/support/` are measured at 100 % in every package** (C5). Why: the crawler's gate
  fails today on a fake method no test calls, because it measures `p2pwatch_testing`; the fold would lose that, and
  the five other packages' `tests/fakes.py` are measured nowhere. No test file mirrors them, so
  `_unit-coverage-check` leaves them out, which it already does: it lists modules under `src` and test files as
  `tests/**/test_*.py`, so a double or a helper is neither (prototype: no change to `coverage_checks`). The crawler's
  two test files that test doubles (`test_fakes.py`, `test_api_fakes.py`) keep their `tests_without_unit` entries and
  follow their doubles. Measured as `--cov=tests` with `tests/**/test_*.py` and `tests/**/conftest.py` omitted:
  `--cov=tests.support` warns in a package where nothing imports it, and the crawler's `tests/integration/conftest.py`
  holds a fixture only the deselected suites run (57 % on `main`).
- **D5. One fake per port, a Writer/Reader pair sharing a store fake, each in the ring of what it replaces** (C4).
  Revises H8 and A16, which put one fake per port at the mirror of its port's file. Why: none of their goals needs
  more. The rename's reach comes from D1, the duplicates go with one place, the name says what is replaced, and a
  contract test runs per port against any implementation. Splitting a pair would make every test build a writer, a
  reader and a shared state for what one object holds today; grouping fakes by adapter instead would tie the tests
  to the composition's cut of the adapters, which a refactoring of the adapters must not touch. A pair's grouping is
  stated by the ports' names (`<Thing>Writer`, `<Thing>Reader`: the reader reads what the writer wrote), so the fake
  follows the ports only. A fake is placed as an adapter for tests: a driven port is implemented by an adapter, a
  driving port by a use case or by the composition (R1), so the fake sits in that ring. A fake mixing unrelated
  ports splits: `FakeCatalogReader` (`DecisionReader` and `ObservationReader`), `FakeDownloadClient`
  (`DownloadClient` and `SourceClient`), `FakeCrawlControls` (`CrawlPauser`, `CrawlResumer`, `ShutdownRequester`).
  Duplicated inline doubles (four `_FakeSourceReader`s, two `_FakeCatalogFileReader`s, ...) become one, in the
  module of doubles of their package until block 70. The layout test checks the place, one double per file named
  after it, and that a fake implementing ports implements one, or one Writer/Reader pair: by test, not by convention.
  (Corrected: from "one `Fake*` class per file", block 70.)
- **D6. The rings of `application/`** (C1), in every hexagon: the ports move from their own ring into
  `application/ports/`, as Hombergs and Graça place them, for familiarity (R12); the use cases and the steps are
  kept apart so that tach keeps the use cases away from the lifecycle's stages (R4, R14). The modules that call no
  port move to `domain/` now, where they are pure: `edge_state`, `source_alerts`, `matching_read` (they import only
  the standard library, `catalog_matching` and `p2pwatch.domain`); `supervise_loops`, which waits on `asyncio` events,
  sits in `steps/` until lot C gives the run state its waits (A1). A15's engine injection and A7's extraction from
  `rejudge_file` are lot C's. `RunCrawler` becomes `CrawlerLifecycle`, `RunPortSyncLoop` `PortSyncLifecycle`, its
  method `run_port_sync_loop` becomes `run`, so it no longer carries a name a rename of
  `PortSyncLoopRunner.run_port_sync_loop` would miss. The ports keep their narrower import list once under
  `application/`: the ignore of `application/ports/**` in `application-imports.yml` moves with them (block 52), or
  every port file fails that rule (5 on `amule_bump` alone, measured). tach's shape, proved on `amule_bump`
  (tach 0.35.3): the layers `composition`, `adapters`, `lifecycle`, `steps`, `use_cases`, `ports`, `domain`, one
  tach module per directory of use cases and of steps, one per port file; tach has no sibling layers, so `use_cases`
  gets a `visibility` of `["*.__main__", "*.composition"]` (the composition is one tach module; `*.composition.**`
  does not match it, measured), which refuses a step's import of a use case. Block 52 keeps today's single
  `application` module, the ports nested in it as their own modules (measured green); block 54 splits it.
  `amule_bump`'s `body` and `release` sit in `use_cases/` beside `bump_amule`, the only module that imports them,
  until lot B's H1 dissolves them: their pure part goes to `domain/`, their reads of `RepoReader` into `BumpAmule`,
  which is what a use case does. They are no steps: a step is a stage of the lifecycle's graph.
- **D7. One port per file, named after it** (C2), in every hexagon. Why: tach can then hold each adapter to exactly
  the ports it uses, which a file of five ports defeats (R9); the name is checked by a test, the only tool that can
  compare a file's name with its class. The port errors go to `domain/`: `client_errors.py`, `repository_errors.py`,
  `CatalogCopyError` (`catalog_copier.py`) and `MergeError` (`catalog_merger.py`); a type both sides use lives there
  (lot 2's rule, as `InvalidConfigError`).
- **D8. Every hexagon's wiring in `composition/`** (C3). The four tooling packages gain the ring; amule's boot and
  port-sync share one composition. `CrawlerApp` becomes `CrawlerComposition`, `PortSyncApp` `PortSyncComposition`:
  what is theirs is the assembly, not the application (R13). Why: `__main__.py` and the composition are one ring
  split in two files only because the crawl's assembly waits for what the command line reads (R15); one entry
  function in every hexagon gives one convention, and R1 is a port implementation, not a second one. The fixed values
  today's `__main__` holds (`_WEBUI_ADDRESS`, `_AMULE_API_ADDRESS`, amule's paths, `_GRYPE_EXECUTABLE`,
  `_GITHUB_API_URL`, `_CHANGELOG_WIDTH_CHARACTERS`) become the composition's constants, as H6 says; R11's "a constant
  of `__main__`" was written when `__main__` was the composition root, and its ledger row is corrected in block 10.
  The process resources it builds (`build_opener()`, `TemporaryDirectory()`) go with the wiring; what it reads of the
  process (`tempfile.gettempdir()`) stays in `__main__`. No `src` module imports a `__main__`: under `root_module =
  "forbid"`, an import tach finds undeclared fails, and no module declares one, so this costs nothing. H2 and H14
  (boot's environment, the duplicated wiring) are lot B's, on the composition this lot gives amule. `vex_checks`'
  `__main__` keeps reading `__file__` until lot B's H3 (the root from `cwd`); it does not move, so its index holds.
- **D9. The layout tests live in the crawler's tests**, beside `test_workspace_dependencies.py`, the precedent for a
  test over the workspace's files.

## Blocks

Estimates from the sizing reports on `main` at `d4180cdf` (appendix), regrouped; each teammate measures its block and
splits it at a bound. Four blocks take the size exemption, which the operator approves on their row: 50, 52 and 70
are purely mechanical, holding moves and renames, the paths that name them (`tach.toml`, the ast-grep globs and
ignores, the docs) and nothing else; 30 is the fold, which also removes a package (D3).

| # | Branch | Holds | Lines, files (est.) |
|---|---|---|---|
| 10 | `chore/pyrefly-in-gate` | this spec; the ledger's R11 row corrected (D8); pyrefly a dev dependency; `[tool.pyrefly]` in each package; `pyrefly-check` in `lint-all`; the gotcha's reason (D1) | 80, 14 |
| 20 | `chore/pytest-settings-plugin` | the `pytest_settings` package, its entry point, tests and `[tool.pyrefly]`; its wiring in the workspace and the gate, outside vulture; C6 (D2). Splits package / wiring at 20 files | 200, 19 |
| 22 | `chore/pytest-settings-applied` | the packages' own `--strict-markers` and filters gone (D2) | 25, 9 |
| 30 | `refactor/fold-crawler-testing` | **exempt, the fold**: `p2pwatch_testing` into the crawler's `tests/fakes/` and `tests/support/`, the package and its configuration removed, the crawler measuring `tests` (D3, D4); the gotcha's place | 200, 85 |
| 32 | `test/fakes-and-support-covered` | `tests` measured in the five other packages; C5 (D4) | 60, 8 |
| 40 | `refactor/fakes-one-per-port` | the fakes mixing unrelated ports split (D5) | 350, 19 |
| 42 | `refactor/inline-fakes-deduplicated` | the duplicated inline doubles made one (D5) | 400, 16 |
| 50 | `refactor/one-port-per-file` | **mechanical, exempt**: the 12 files bundling ports split, every hexagon; the port errors to `domain/` (D7) | 1300, 125 |
| 52 | `refactor/application-rings` | **mechanical, exempt**: `ports/` into `application/ports/` with its ast-grep ignore; `use_cases/`, `steps/`, the lifecycles; the three pure modules to `domain/`; `CrawlerComposition`, `PortSyncComposition`, `CrawlerLifecycle`, `PortSyncLifecycle`, `run` (D6, D8) | 1200, 260 |
| 54 | `chore/ring-rules` | tach's layers, modules and visibility for the rings; the test of one port per file; C1, C2 in `AGENTS.md` (D6, D7) | 150, 8 |
| 60 | `refactor/crawler-composition` | `build_command_line` in the crawler; `AGENTS.md`'s "bind fixed in `__main__.py`" (D8) | 250, 7 |
| 62 | `refactor/amule-composition` | the same for `p2pwatch_amule` (D8) | 350, 7 |
| 64 | `refactor/vex-template-composition` | the same for `vex_checks` and `template_checks` (D8) | 330, 10 |
| 66 | `refactor/bump-coverage-composition` | the same for `amule_bump` (D8) (Corrected: narrowed to `amule_bump`, split at the line bound) | 390, 11 |
| 68 | `refactor/coverage-composition` | the same for `coverage_checks`; C3 in `AGENTS.md` (D8) (Corrected: split from 66 at the line bound) | 305, 11 (measured) |
| 70 | `refactor/fakes-in-their-ring` | **mechanical, exempt**: one file per fake in the ring of what it replaces, the doubles defined in test modules moved there, every package (D5) | 4000, 170 |
| 72 | `test/fakes-layout` | the test of the doubles' layout; C4 in `AGENTS.md` (D5, D9) | 150, 4 |
| 90 | `docs/test-tooling-and-layout-wrap` | closing block: the holistic findings, backlog, handoff | |

- The tooling comes first so that the layout's renames reach the fakes (D1). The fakes move into their ring (70)
  after the ports have (52), so that no fake moves a third time (30 moves the crawler's, 70 splits every package's);
  the splits (40, 42) come before, since they do not depend on paths.
- 32 follows 30 (the crawler's measure first); 54 follows 52 (the rules on the moved tree); 60 to 68 follow 52 (the
  renamed compositions); 72 follows 70.

## Acceptance

1. **pyrefly fails on a broken import**: an injected `from tests.fakes.nowhere import X` in each package's tests
   fails `uv run poe pyrefly-check`; the tree passes. On `main` the task does not exist.
2. **The plugin applies everywhere**: a hand-run `uv run pytest --no-cov` in each of the seven packages with tests
   refuses an injected test marked `@pytest.mark.misspeled`, and fails on an injected test that calls
   `sqlite3.connect(":memory:")` then `gc.collect()`. On `main` the crawler fails both, amule and matching the first
   only, the four others neither.
3. **The doubles are measured**: an injected method no test calls, in a fake of each package that has doubles (the
   crawler, amule, `vex_checks`, `template_checks`, `coverage_checks`, `amule_bump`), and an injected unused function
   in the crawler's `tests/support/`, each fail the gate. On `main` only the crawler's fake fails it.
4. **The rings**: `find packages -path '*/src/*' -type d -name ports -not -path '*/application/*'` prints nothing
   (on `main`: 6). With the injected import also declared in the importer's `depends_on`, so that only the rings can
   refuse it, `tach check` fails for a use case importing a step and a step importing the lifecycle (`Layer ... is
   lower than layer ...`), and for a step importing a use case (`... does not match its visibility`).
5. **One port per file**: the test fails on an injected second port class in a port file, and on a port file renamed
   away from its class.
6. **The composition**: every `__main__.py` imports from its package's `composition/` only, beside the standard
   library (`grep -n "^from\|^import" packages/*/src/*/__main__.py`); each hexagon has
   `composition/command_line.py` with `build_command_line`.
7. **The doubles' layout**: the test fails on an injected `Fake*` class placed under the wrong ring, on a file
   holding two `Fake*` classes, and on a fake implementing two unrelated ports.
8. **The rename reaches the fakes**: a Serena `rename_symbol` from `RepoReader.read_file` and from
   `VexReader.read_claims`, run on a scratch branch, leaves `git grep -w <old name> -- packages/` empty. On `main` it
   leaves 3 sites each (9 of 12, 8 of 11 reached).
9. **Nothing out of scope changes**: the diff shows no change under `deploy/`, `security/`, the crawler's
   `migrations/`, `packages/amule/docker/`, the Dockerfiles and `.github/workflows/`; CI's integration suites pass on
   both architectures at the top.
10. **The gate is green** at every block.

## Backlog

- **Contract tests for the fakes** stays open and follows lot C (the handoff's order): this lot gives the fakes their
  place, lots B and C their names and ports' final shape.
- **The ast-grep rule tests bound to their rules by design** stays open: this lot only moves the globs it touches.
- **Adopt ty** stays open: pyrefly here checks imports for Serena's sake; ty's parity conditions are unchanged.
- **Test quality** and **Mutation testing in the gate** stay open: this lot moves tests, it prunes none.
- **A copy before a migration that rewrites rows** stays open and ships before the next release; this lot ships no
  image change, so it releases nothing.
- **Multi network, stage 5**, **Sort the files view by first seen**, **The webui in the visitor's time zone**,
  **The Grype scan back on p2pwatch at the v5 release**, **The VEX's Python claims applied by Grype**, **The metrics
  served by the webui on 8080**, **Every stamp an integer of microseconds** and **The node page shows a node id set in
  `crawler.yml`** stay open: none touches what this lot changes.

## Appendix: measurements

Taken on `main` at `d4180cdf` on 2026-10-22 by four Sonnet sizing agents and one Opus prototype agent (reports kept
in the lead's scratchpad), recounted by the spec's review (`.reviews/lot-a-spec.md`). Re-run before acting on one.

- Files naming `<pkg>.ports`, importers and port files: p2pwatch 132, p2pwatch_amule 26, vex_checks 23,
  template_checks 14, coverage_checks 13, amule_bump 20.
- Port files 70, port classes 86; 12 files bundle 2 to 5 ports (`catalog` 5, `client_status` 3, `node_id` 3,
  `telemetry` 3, eight with 2); the 56 single-port files are already named after their class.
- `application/` modules in the six hexagons: 38: 21 use cases, 11 steps, 2 lifecycles, 4 that call no port.
- `p2pwatch_testing`: 13 files, 1540 lines; 56 importer files. Doubles defined in test modules: 22 `Fake*` classes in
  17 files, plus 7 driving-port fakes.
- The ledger as one lot: about 67 blocks (tooling 8, layout 13, names 26, design 20). Regrouped with the mechanical
  exemption: A 17 blocks (Corrected: 18, block 66 split at the line bound); B about 12 (one mechanical block of renames, about five normal blocks of names, five of the
  other hexagons, the closing one); C about 16 (the design sizing's 21 with its closing one, less the other hexagons'
  five).
