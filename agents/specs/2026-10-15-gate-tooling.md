# Gate tooling (lot 1 of the gate tooling, Serena and test quality umbrella)

- Date: 2026-10-15. Status: approved by the operator (2026-10-15); spec review answered
  (`.reviews/gate-tooling-spec.md`: 1 critical, 5 major, 19 minor; all corrected, the metric's content (L9) by
  the operator's choice, but the last minor, lots 2 and 3's measurements, which their specs re-run).
- Tier: Spec (the operator, 2026-10-14). Operator surfaces: one new metric, `p2pwatch_search_results_skipped`
  (L9); the webui's file page shows the coverage values of a decision (L8).
- Origin: lot 1 of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md` (D12), whose decisions D1, D2 and
  D6 to D10, D16 and D17 this lot carries out. That umbrella spec is cited as "U-D<n>" below.
- Evidence: the code on `main` at `307de0b`; three probes run on scratch copies on 2026-10-15 (`layout-probe`,
  `deps-probe`, `deadcode-probe`), with uv 0.12.23, deptry 0.25.1, vulture 2.16, ast-grep 0.50.0, ruff 0.16.9,
  mypy 2.3.1, poethepoet 0.48.0. Their facts are restated where a decision rests on them. Paths under
  `packages/crawler/src/p2pwatch/` unless noted.

## At a glance

- **Four checks join the gate**: `dependency-check` (deptry), `code-pattern-check` (ast-grep),
  `dead-code-check` (vulture), and `unit-coverage-check` (coverage per unit, U-D1), beside the existing ones.
- **The tests mirror `src`** (U-D2): every test directory becomes a package, mypy runs once per package, 25 test
  files move and 5 split, and a test file that maps to no module fails the check unless it is listed with its
  reason (L4).
- **Three tooling packages and one support package**: `vex_guards` becomes `vex_checks` (U-D10),
  `template_checks` and `coverage_checks` are new (U-D9), and the crawler's shared test support moves into a new
  `p2pwatch_testing` (L6).
- **The dead code goes**: what only tests reach is deleted or moved (L7); a computed field nobody shows is
  shown (L8); a counter nobody reads becomes a metric (L9); a `getattr` on a policy-named field becomes a typed
  accessor table (L10).

## 1. Why

The operator wants the gate to hold what review alone cannot: that every module is tested by its own unit
tests, that no code lives only for its tests, that each package declares what it imports, and that no code
reads attributes by name. U-D1 to U-D17 settle what; this spec settles how, block by block.

## 2. Scope

In: U-D1, U-D2, U-D6 to U-D10, U-D16 for this lot's tasks, U-D17; the support package (L6); the three
dead-code arbitrations (L7 to L9); the gaps U-D1's check finds (L5).

Out, to lot 3: U-D3's unique coverage and its check, the pruning (U-D4, U-D5, U-D14, U-D15), mutmut and
`mutation-check` (U-D13), and the two flaky tests D14 names besides `sqlite3.connect` (`test_disk_space`, the
log count in `test_search_pacing.py`) with the repository root lookup. Out, to lot 2: Serena and the language
servers (U-D11).

## 3. Decisions

- **L1. Every test directory is a package, and mypy runs once per package.** An `__init__.py` goes in every
  `tests/` directory and subdirectory (not in data directories such as matching's `tests/fixtures`); test modules
  become `tests.<mirror>`. `type-check` becomes a sequence of `{ cmd = "mypy src tests", cwd = "packages/<pkg>" }`
  like `test`; the root `[tool.mypy]` keeps `python_version` and `strict`, and loses `files` and its comment.
  `catalog_matching` gains an empty `py.typed` (the crawler's run sees it as installed: 61 `import-untyped`
  errors without it), and so do `p2pwatch` (seen as installed by `p2pwatch_testing`'s run) and
  `p2pwatch_testing` (seen by the crawler's run). Every workspace package, the new ones included, has its own
  `type-check` entry: a `py.typed` package is trusted by its importers, so its own strict run is the only one that
  reports its errors. amule_bump's three `from fakes import` become `from tests.fakes import`; ruff's `src` list
  drops the five `tests` entries. Why: mirroring `src` creates same-named test files (amule's `boot/test_main.py`
  and `port_sync/test_main.py`), which today's flat layout and single mypy run refuse (`Duplicate module named
  "test_main"`; and with `__init__.py` but one run, `Duplicate module named "tests"`); the probe passed
  `uv run poe check` with this configuration and the 26 moves, test counts unchanged (349, 1415, 133, 73, 54).
  Rejected: `explicit_package_bases` with `mypy_path`, and `__init__.py` in subdirectories only, which both work
  but keep a basename rule across packages that the new packages make likelier to bite;
  `--import-mode=importlib`, which fixes pytest only. Cost: mypy 3.4 s to 8.5 s cold, 0.14 s to 0.55 s warm.
- **L2. The mapping rule.** `src/<pkg>/a/b.py` is covered by `tests/a/test_b.py` and `tests/a/test_b_<aspect>.py`;
  a test file belongs to the longest stem it matches in its directory (`test_b_c.py` goes to `b_c.py` when it
  exists, else to `b.py`). A dunder drops its underscores: `a/__main__.py` maps to `tests/a/test_main*.py` (today's
  convention), `a/__init__.py` to `tests/a/test_init*.py`; a module named `main.py` or `init.py` beside them is
  refused by the check (none exists). Why: mechanical, so the check and a reader apply the same rule; "aspect"
  files keep large test modules splittable.
- **L3. What U-D1's check measures.** For each module, coverage.py's own analysis (statements and branches, as
  `--cov-fail-under` counts them), read through its public API (`Coverage.json_report(morfs=[module],
  contexts=[...])`, not the private `_analyze`), restricted to the module's **own tests**: the test files L2 maps
  to it. A module's top-level statements (outside any function, found statically from its syntax tree) count as
  covered when any context ran them, since pytest-cov attributes a module's import to whichever test first
  imported it. A module no test runs is satisfied when import covers it (a `Protocol` port, an `__init__.py`, an
  errors module); no other exemption. `own tests` joins `AGENTS.md`'s glossary. Each package's pytest run records
  per-test contexts (`--cov-context=test`), and `unit-coverage-check` runs inside the `test` sequence, after each
  package's pytest, so CI's existing `poe test` step runs it. `--cov-fail-under=100` stays. Why: raw arcs also
  flag multi-line expressions and exit arcs coverage never counts as branches (the probe saw them in 6 modules
  whose analysis is clean); inside `test`, CI needs no new step; per-test contexts cost about 8% (crawler 19.9 s
  to 21.6 s).
- **L4. A test file that maps to no module fails the check**, unless its package lists it in
  `[tool.coverage_checks] tests_without_unit`, each entry with its reason. Listed today: the 16 SQL migration
  tests and `test_append_only` (their subject is SQL), `test_golden_corpus` and `test_prod_targets` (their subject
  is `deploy/` data), `test_fakes.py` (its subject is `p2pwatch_testing`, L6), and `tests/integration/` (excluded
  by marker anyway). Why: the operator's choice
  (2026-10-15) of a convention enforced both ways; without it a misnamed test file silently stops counting.
- **L5. The gaps are closed by direct tests, no module split.** After the moves, five crawler modules are short
  of their own tests (the probe's measure, L3):

  | Module | Short | Covered today by |
  |---|---|---|
  | `adapters/mule_api/errors.py` | 21 of 33 statements, 10 of 10 branches (`error_from_response`, `_error_code_and_message`) | `test_client.py`, `test_client_search_pacing.py` |
  | `adapters/persistence_sqlite/errors.py` | the except arm of `wrap_sqlite_errors` | repository and webui tests |
  | `webui/adapters/catalog_read.py` | 2 statements, 2 branches (unknown source or name) | `webui/composition/test_app.py` |
  | `application/search_worker.py` | 1 statement (`run_task` when not connected) | `composition/test_app.py`, `application/test_search_tasks.py` |
  | `merge/merger.py` | 1 branch (`--into` skips the output when it is a source) | `merge/test_main.py` |

  Each gets a direct test; `adapters/mule_api/test_errors.py` also receives 3 hierarchy tests from
  `ports/test_client_errors.py`. Why: each gap is a case reached only from a higher-level test, not a group of
  code living in the wrong file.
- **L6. The crawler's shared test support becomes a workspace package, `p2pwatch_testing`** (directory
  `packages/crawler_testing`, dist `p2pwatch-testing`), never shipped and imported only by the crawler's tests: `tests/application/fakes.py`,
  `tests/adapters/mule_api/api_fakes.py`, `tests/virtual_time.py`, `tests/catalog_rows.py`,
  `tests/adapters/persistence_sqlite/older_catalog.py`, `tests/merge/helpers.py` (872 lines). It declares
  what its modules import (`p2pwatch`, `pytest`, `httpx`) as runtime dependencies, joins `dependency-check` with
  its own `[tool.deptry]` (pass A only: it has no tests of its own) and `type-check` (L1); the crawler's `dev`
  group declares it (L12's root sources). Its coverage is measured by the crawler's whole suite at 100% (the crawler's pytest run adds
  `--cov=p2pwatch_testing`), without U-D1's ownership: the three dead lines and the dead branches the suite never
  runs (in `api_fakes.py`, `merge/helpers.py`, `virtual_time.py`) are deleted. `test_fakes.py` stays in the
  crawler's tests, listed under L4 ("tests `p2pwatch_testing`'s fakes"). vulture does not scan it (only tests
  call it; its coverage rule already forbids dead support code). amule_bump's 17-line `fakes.py`, without logic,
  stays in its tests. Why: the operator's choice (2026-10-15), Python's equivalent of Gradle's `testFixtures`
  under the conventions every tool expects; unit tests of fakes would prove only that a fake does what its code
  says, so the guarantee that a fake behaves as the real adapter goes to a backlog entry (contract tests, section
  7).
- **L7. What only tests reach is deleted or moved** (U-D6): `domain/download/states.py`'s `is_terminal` (its 2
  tests; production does it in SQL), `ReaderProvider.quiesce` in `adapters/persistence_sqlite/reader.py` (the
  method, `_quiesced`, `_lock`, `_connections`, its error branch, 3 tests and 3 cleanups; a seam for a swap no
  backlog entry plans), `MatchingEngine.evaluate` (its 25 test calls become `evaluate_file((candidate,))`, the
  entry production uses; `packages/matching/AGENTS.md` and `docs/contributing/architecture.md` follow), and
  amule_bump's `GITHUB_BODY_MAX_CHARACTERS`, moved into `test_body.py`. `open_reader`'s
  `check_same_thread=False` loses its stated reason with `quiesce` (its docstring cites it); its remaining user is
  test-side: `tests/webui/conftest.py` closes every reader connection at teardown from the main thread, which
  `check_same_thread=True` would turn into a suppressed `ProgrammingError` and a silent leak. By U-D6's logic a
  reason that exists only for tests is none: block 70 sets `check_same_thread=True` and changes that fixture, or
  stops as a defect class 2 question if production needs it. Why: these serve no production path.
- **L8. `Explanation.coverage_values` is shown** on the webui's file page, beside the rules, tokens and vetoes
  the page already shows. Why: the operator's choice (2026-10-15); the MVP design meant each decision's coverage
  values to be explainable, and they serve the tuning of the policy's thresholds.
- **L9. The skipped search results become a metric**, `p2pwatch_search_results_skipped` (a counter, exposed with
  `_total`, labelled like `p2pwatch_searches`): the count of whole results the mapper discards (no hash, no
  usable size, not an object) travels with the search's result to the use case that emits `SearchExecuted`,
  which carries it; the policy adds it to the counter. An alternate name without a name is dropped as today and
  counts nothing: the mapper's current count mixes both, and a drift of the protocol shows as discarded results
  (the operator, 2026-10-15). This changes a port: `SearchClient.search` (`ports/search_client.py`) returns the observations and the
  skipped count instead of the observations alone, for its 9 implementations (the client and test fakes) and
  33 call sites. `AmuleApiClient.skipped_results`, a counter held by the adapter, goes. `docs/operate.md` lists
  the metric. Why: the operator's choice (2026-10-15); it is the only signal of a drift in amuleapi's answers, which
  today would discard every result silently, and a metric shows its rate where a log would drown it.
- **L10. A typed accessor table replaces `ATTR_NAMES` and the `getattr`** in `packages/matching/src/
  catalog_matching/matchers.py`: each name the policy's `attr_between` accepts maps to a function reading its
  `FileCandidate` field, so mypy and vulture see every read. `reader.py`'s `getattr` on a `threading.local`
  becomes a typed `threading.local` subclass; the three uses in tests (two `hasattr` asserting a field's absence,
  one `setattr` in a loop) are rewritten. The ast-grep rule matches any reference to the four names, an alias
  (`f = getattr`) included, except as an attribute name (`obj.getattr`); ruff's `banned-api` bans the written-out
  forms (`builtins.getattr` and the three others), which only it sees. Why: U-D17, and `FileCandidate.size_mib`
  looked dead to vulture only because of the `getattr` (the operator, 2026-10-15); a rule on calls alone lets
  `builtins.getattr(...)` and an alias through.
- **L11. The tasks.**

  | Task | Command | In | Time |
  |---|---|---|---|
  | `dependency-check` | per package, `deptry src` then `deptry --non-dev-dependency-groups dev src tests` | `lint-all`, after `format-check` | 0.8 s |
  | `code-pattern-check` | `ast-grep scan` with the versioned `sgconfig.yml` and rule `no-dynamic-attribute` | `lint-all` | not measured |
  | `dead-code-check` | `vulture --ignore-names ${TEMPLATE_READ_NAMES}`, the names captured by poe's `uses` from `_template-read-names` (`python -m template_checks.read_names <templates dir>`) | `lint-all` | 0.35 s |
  | `template-check` | `python -m template_checks.check_templates <templates dir>` | `lint-all`, unchanged place | unchanged |
  | `unit-coverage-check` | `python -m coverage_checks.unit_coverage` per package | `test`, after each package's pytest | not measured |
  | `type-check` | per package, `mypy src tests` (L1) | `lint-all`, unchanged place | 8.5 s cold |

  vulture runs once over every package's `src` but `p2pwatch_testing`'s (L6), with a root `vulture_whitelist.py`
  (the four library hooks, each with its reason; ruff's per-file ignores `B018` and `F821` for it), because one
  package's API is kept alive by another: on `matching/src` alone it reports 15 findings instead of 3
  (`build_ed2k_link`, every `Explanation` field). Why: U-D16's names; inside `lint-all` and `test`, so the
  pre-push hook and CI, which call those, need no change.
- **L12. deptry runs twice per package** with `[tool.deptry]` in each package: `exclude = ["\\.venv"]` (it
  replaces the default list, whose `tests` pattern silently drops the tests root; a one-line comment says so),
  `per_rule_ignores = { DEP002 = ["pytest-cov"] }` (plus `pytest-asyncio` for the crawler: entry-point plugins,
  never imported), and `known_first_party = ["tests"]` once a package's tests are a package (L1). Each member
  names its test group `dev`: the root's existing `uv sync --dev` then installs every member's `dev` group, so
  `scripts/setup-dev.sh`, the pre-push hook, `.github/actions/setup-uv-env` and every workflow are unchanged. The
  root `dev` group keeps deptry, mypy, poethepoet, ruff, sqlfluff, types-pyyaml (mypy's input), zensical, plus
  this lot's vulture and ast-grep-cli; pytest, pytest-cov, pytest-asyncio and the members leave it. Root
  `[tool.uv.sources]` ends the lot with three entries: `catalog-matching` (the crawler's runtime dependency),
  and, from block 100 (Corrected 2026-10-15, at block 30: not 80, a number left from before the blocks were
  renumbered), `p2pwatch` and `p2pwatch-testing` (the crawler's `dev` group depends on
  `p2pwatch-testing`, which depends on `p2pwatch`: without both entries `uv lock` refuses the cycle). Why: deptry
  has no notion of test code (DEP004 fires on any scanned file importing a dev-only package, DEP002 never checks
  dev dependencies, from its source), so the first pass checks `src` against runtime dependencies and the second
  checks the tests against the `dev` group; and both Dockerfiles exclude test dependencies with `UV_NO_DEV=1`,
  which excludes the `dev` group and nothing else, so a group named otherwise (`test`, even installed by a root
  `[tool.uv] default-groups`) would enter both images. (Corrected 2026-10-15, after the spec review: the first
  reason given, that a `test` group would need new `uv sync` flags, was false.)
- **L13. The images stay as they are**, and `UV_NO_DEV=1` becomes load-bearing in both Dockerfiles: without it,
  `--package p2pwatch` would install the crawler's test group. A one-line comment says so in each. Why: the probe
  ran both Dockerfiles' exact sync commands before and after: the same installed sets (crawler 23 packages,
  amule 1, the crawler's frozen layer 21).

## 4. Blocks

Estimates from the probes (2026-10-15), not a diff: read them as plus or minus 30 %.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `refactor/vex-checks` | U-D10: `vex_guards` to `vex_checks` and the whole `guard` family to `premise`; the umbrella spec, this spec and the three `BACKLOG.md` entries of section 7 | 330, 35 |
| 20 | `refactor/template-checks` | U-D9's `template_checks` (`packages/template_checks`) with `check_templates` moved unchanged from `webui/_dev`, which goes; `template-check` rewired | 200, 12 |
| 30 | `chore/dependency-check` | L12, L13: the `dev` groups, the root group trimmed, deptry and `dependency-check`, the Dockerfile comments | 150, 13 |
| 40 | `refactor/no-dynamic-attribute` | U-D17 and L10: ast-grep, `code-pattern-check`, the `banned-api` entries, the accessor table, the typed `threading.local`, the three tests | 160, 10 |
| 50 | `feat/coverage-values-shown` | L8 | 80, 5 |
| 60 | `feat/skipped-results-metric` | L9, the `SearchClient.search` port change included | 300, 18 |
| 70 | `refactor/test-only-code` | L7: the deletions and moves | 200, 15 |
| 80 | `chore/dead-code-check` | U-D6, U-D7: vulture, `template_checks.read_names`, the root `vulture_whitelist.py`, `dead-code-check` | 200, 8 |
| 90 | `test/test-packages` | L1: the `__init__.py`, mypy per package, the `py.typed`, ruff's `src`, amule_bump's imports, L12's `known_first_party` | 120, 25 |
| 100 | `test/testing-package` | L6: `p2pwatch_testing`, the six modules moved, the crawler's test imports, the dead support code | 400, 40 |
| 110 | `test/mirrored-layout` | L2: the 25 moves and 5 splits | 250, 35 |
| 120 | `test/unit-gaps` | L5, and the `sqlite3.connect` test fixed so that per-test contexts can be recorded | 200, 8 |
| 130 | `test/unit-coverage-check` | U-D1, L3, L4: `coverage_checks` (`packages/coverage_checks`), the per-test contexts, `unit-coverage-check` in `test`, the `tests_without_unit` lists, `own tests` in the glossary | 400, 14 |
| 140 | `docs/gate-tooling-wrap` | the closing block (Wrap): the handoff, `BACKLOG.md` reconciled | |

- **Blocks 10, 100 and 110 pass 20 files** under the one-line exemption: mechanical renames and moves (the
  operator, 2026-10-13). **Block 90 passes 20 files** under the same exemption: most of its files are empty
  `__init__.py`. (Corrected 2026-10-15, after the spec review: the deletions left the dead-code check's block,
  now 70 and 80, and the rewiring left the moves' block, now 90 and 110; block 60 grew with the port change.)
  (Corrected 2026-10-15, at block 10's pull request: block 10 passes 500 lines too, 544, since five renamed
  files fall below git's 50 % rename similarity and count as deleted and added; 235 with `-M20%`.)
- **Each block updates the documents its change contradicts**: `AGENTS.md` (the package list and count, the
  gate's sub-tasks, the tooling split, the layout of tests), `docs/contributing/testing.md`, `docs/operate.md`
  (L9), and the packages' own `AGENTS.md`.

### Order

- The renames and the new packages come first (10, 20), so later blocks write the final names.
- deptry (30) precedes the test packages (90), which then add `known_first_party` where tests become packages.
- The dead code goes (50 to 70) before vulture enters the gate (80), and before the tests move (100, 110), so no
  deleted test is moved first.
- The test packages and mypy per package (90) precede the support package (100), which needs its own
  `type-check` entry, and the moves (110), which create same-named test files.
- The gaps (120) close before the check (130) enters the gate, so each block is green alone.

### Transient states inside the stack

- Blocks 20 to 70: `template_checks` exists without `read_names`, which block 80 adds.
- Blocks 30 to 90: the crawler's support modules are still under `tests/`, outside every coverage measure, as on
  `main`.

### Surfaces whose consumer arrives in a later block

None: each task enters the gate with the block that makes it pass.

## 5. Acceptance

Each criterion names what would prove it wrong.

1. **Each new check fails on a seeded violation and passes on the tree** (the block report quotes both runs):
   - `dependency-check`: `import httpx` in amule's `src` gives `DEP003` (transitive), `pyyaml` dropped from
     matching's `dev` group gives `DEP003 'yaml'` on `tests/test_engine.py`, `import pytest` in a `src` gives
     `DEP004`; each exits non-zero.
   - `code-pattern-check`: a `getattr(x, name)` in a `src` and in a test exits non-zero; a method named
     `obj.getattr(...)` passes; the same call under `# ast-grep-ignore: no-dynamic-attribute` passes.
   - `dead-code-check`: an unused function in a `src` exits non-zero; the same in a test passes; removing one
     template's read of a view field reports that field.
   - `unit-coverage-check`: a branch of `domain/search/backoff.py` covered only from another module's test exits
     non-zero naming the module; a test file `tests/domain/test_nothing.py` exits non-zero as an orphan; listing
     it under `tests_without_unit` passes.
   - `type-check` (block 90): a seeded untyped `def` in one package's `tests` exits non-zero with
     `[no-untyped-def]`, and so does one in `p2pwatch_testing` (block 100).
2. **The layout holds**: every `tests/` directory but data directories has an `__init__.py`; no test module
   imports `fakes` bare; `unit-coverage-check`'s output on the tree counts N test files mapped to a module and M
   entries of `tests_without_unit`, and N + M equals
   `git ls-files 'packages/*/tests/*' | grep -c '/test_[^/]*\.py$'` minus the files under `tests/integration/`.
3. **No dynamic attribute access**: `ast-grep scan` lists 5 findings on `main` (`matchers.py:129`,
   `reader.py:66`, `test_events.py:30`, `test_crawler_config.py:660` and `:661`) and none after block 40.
4. **The images are unchanged**: CI's image builds and compose smoke pass on amd64 and arm64; the report of the
   last block before the closing one lists the installed packages of each image on `main` and at the top of the
   stack, which match (blocks 20, 100 and 130 add workspace members, block 100 one the crawler's `dev` group
   declares).
5. **The rename is complete** (block 10): `git grep -n -e vex_guards -e vex-guards -- ':!agents'` prints nothing
   (on `main`, 32 files); `git grep -n -i guard -- packages/vex_checks SECURITY.md .github` prints nothing; the
   block report quotes `grype-scan.yml`'s two commands (`check_image_claims`, `check_stale_claims`) and
   `release.yml`'s run locally against the renamed package, since no pull request runs them (cron and pushes to
   `main` only).
6. **The metric**: a search whose answer holds a result without a hash increments
   `p2pwatch_search_results_skipped_total` with that search's labels; one without unusable results does not.
7. **The coverage values**: a file page whose decision fired a `coverage` token shows its value.
8. **The gate**: `uv run poe check` passes at each block's tip; `uv run poe docs-build` passes where a block
   touches `docs/`.

## 6. Risks and accepted limits

- **vulture is name-based**: the 97 names templates read hide any other definition with the same name, and a
  stale whitelist entry is never reported.
- **The template guard keeps its regular expressions** in this lot (section 7).
- **`p2pwatch_testing` is held to coverage, not to correctness**: a fake that differs from its adapter passes
  (section 7).
- **mypy is slower**: 8.5 s cold instead of 3.4 s (L1).
- **ast-grep sees names, not bindings**: a local function or variable named like one of the four builtins would
  be reported too; none exists today.

## 7. Adjacent backlog items

- Existing entries (multi network stage 5, sort by first seen, the copy before a migration, the webui in the
  visitor's time zone, stamps in microseconds, the webui's read side): stay open, none concerns this lot.
- **Added by this lot, with the operator's agreement (2026-10-15)**:
  - Mutation testing in the gate, as U-D13's impact-scoped design.
  - The logic-free template guard on Jinja's syntax tree: it would flag 4 `or ""` in `node.html` and 8
    `{% for url in (nav.prev_url,) if url %}` loops in `files`, `sources`, `source_detail`, `source_name`, whose
    logic moves into the views.
  - Contract tests for the fakes: one suite per port, run against the fake and the real adapter.
