# Handoff: gate tooling, lot 1 of the gate tooling, Serena and test quality umbrella

Drafted by block 135 from the lot's block reports (#230 to #243, and block 135's own) and the lead's lot notes;
corrected by block 150, the top of the closing block's split, which adds the holistic review and its exits.

## State

Tier Spec lot, operator surfaces included: the metric `p2pwatch_search_results_skipped`, the coverage values
on the webui's file page, and the `merge` CLI's log line per source catalog. Spec
`agents/specs/2026-10-15-gate-tooling.md`, approved by the operator on 2026-10-15 after the spec review
`.reviews/gate-tooling-spec.md` (1 critical, 5 major, 19 minor). All were answered, except the last minor,
lots 2 and 3's measurements, which their own specs re-run. The lot carries out lot 1 of the umbrella spec
`agents/specs/2026-10-14-gate-tooling-and-test-quality.md` (U-D1, U-D2, U-D6 to U-D10, U-D16, U-D17).

Sixteen blocks, one stack cut from `main` at `307de0b`:

| Block | PR | Branch |
|---|---|---|
| 10 | #230 | `refactor/vex-checks` |
| 20 | #231 | `refactor/template-checks` |
| 30 | #233 | `chore/dependency-check` |
| 40 | #234 | `refactor/no-dynamic-attribute` |
| 50 | #235 | `feat/coverage-values-shown` |
| 60 | #236 | `feat/skipped-results-metric` |
| 70 | #237 | `refactor/test-only-code` |
| 80 | #238 | `chore/dead-code-check` |
| 90 | #239 | `test/test-packages` |
| 100 | #240 | `test/testing-package` |
| 110 | #241 | `test/mirrored-layout` |
| 120 | #242 | `test/unit-gaps` |
| 130 | #243 | `test/unit-coverage-check` |
| 135 | #244 | `test/unit-coverage-measure` |
| 140 | opened with 150 | `docs/gate-tooling-wrap` |
| 150 | the stack's top | `refactor/holistic-fixes` |

The closing block split when it passed the files bound: 140 (`docs/gate-tooling-wrap`) holds the holistic
review's documentation fixes and `BACKLOG.md`; 150 (`refactor/holistic-fixes`), on top, its code fixes, the
spec's notes and this handoff. Block 135 was inserted when block 130 passed both size bounds (Decisions below).

Nothing of the stack is merged. `git tag -l 'v*'` still ends at `v4.1.0`. Neither database's schema changes:
no migration in the lot.

Once merged, `uv run poe check` holds these checks besides ruff, mypy, sqlfluff and the template check:
- `dependency-check` (deptry, twice per package);
- `code-pattern-check` (ast-grep: no `getattr`, `setattr`, `hasattr`, `delattr`, nor the `builtins` module);
- `dead-code-check` (vulture over every `src`, with the names the templates read);
- per-package mypy over `src` and `tests`;
- `unit-coverage-check`: each module covered by its own tests, the test files mirroring `src`.

The workspace grows to eight members: `vex_checks` (renamed from `vex_guards`), `template_checks`,
`coverage_checks` and `p2pwatch_testing` are never shipped. Test counts at the tip: matching 350, crawler 1400
(14 deselected), amule 133, vex_checks 73, template_checks 32 (35 before block 150), coverage_checks 34,
amule_bump 54. On `main` they were 349, 1415, 133, 73 and 54.

## What was built

- **`vex_checks`** (block 10): `vex_guards` renamed, and its `Guard` family renamed `Premise` (`PREMISES`,
  `SourcePremise`, `ImagePremise`, `is_source_premise`, `evaluate_source_premises` and their image twins).
  `TypeIs` replaces `TypeGuard`. The workflows' module paths follow; the poe task and job names stay. The
  lot's two specs and three `BACKLOG.md` entries ship in its first commit.
- **`template_checks`** (block 20): `check_templates` leaves `p2pwatch.webui._dev`, which the crawler image
  installed, for its own member; `template-check` runs `python -m template_checks.check_templates`.
- **`dependency-check`** (block 30): deptry in `lint-all`, running twice per package. The first pass checks
  `src` against the runtime dependencies, the second `src` and `tests` against those plus the `dev` group.
  - Each member has its own `dev` group; the root's keeps the workspace's tools only.
  - Each `[tool.deptry]` sets `exclude = ["\\.venv"]`, since deptry's default exclusions drop `tests`, and
    ignores the pytest plugins.
  - `UV_NO_DEV=1` is now load-bearing in both Dockerfiles, a comment says so.
- **No dynamic attribute access** (block 40): `code-pattern-check` runs ast-grep's rule `no-dynamic-attribute`
  (`sgconfig.yml`, `ast-grep-rules/`), which refuses the four builtins, any import of `builtins` and
  `__builtins__`. Its five uses went:
  - the matcher's `getattr` became `READERS_BY_ATTR`, a typed accessor table that replaces `ATTR_NAMES`;
  - the reader provider's `threading.local` became `ThreadLocalConnection`;
  - three tests were rewritten.
- **The coverage values shown** (block 50): the file page lists every `coverage` token of the decision's
  explanation with its value to two decimals (`TokenCoverage` view rows); `docs/operate.md` names them.
- **`p2pwatch_search_results_skipped`** (block 60): `SearchClient.search` returns a `SearchAnswer`, the
  observations and the count of results that yield none. `SearchExecuted` carries the count, and the policy
  adds it to a counter labelled like `p2pwatch_searches`, by 0 on a clean search.
  `AmuleApiClient.skipped_results` is gone. `docs/operate.md` lists the counter.
- **What only tests reached** (block 70): `ReaderProvider.quiesce` (with its lock, its registry and its error),
  `is_terminal` and `MatchingEngine.evaluate` were deleted; amule_bump's `GITHUB_BODY_MAX_CHARACTERS` moved into
  `test_body.py`. `open_reader` keeps sqlite3's same-thread check, and a test pins it.
- **`dead-code-check`** (block 80): vulture runs once over every `src` but `p2pwatch_testing`'s.
  - `template_checks.read_names` lists, from Jinja's syntax tree, the names the templates read; poe passes them
    as `--ignore-names` through a `shell` task.
  - The root `vulture_whitelist.py` holds the four library hooks, each with its reason.
  - `AGENTS.md` gains the rule "No code only tests reach".
- **Test packages** (block 90): an `__init__.py` in every `tests/` directory; `type-check` runs mypy once per
  package over `src` and `tests`; matching ships a `py.typed`; amule_bump imports `tests.fakes`;
  `known_first_party = ["tests"]` everywhere; `.dockerignore` matches the per-package caches.
- **`p2pwatch_testing`** (block 100, `packages/crawler_testing`): the crawler's six shared test support modules
  become a member that only the crawler's `dev` group declares.
  - Its coverage is measured by the crawler's suite (`--cov=p2pwatch_testing`); its dead lines and branches
    were deleted.
  - It has its own `type-check` entry, beside `p2pwatch`'s new `py.typed`, and stays out of vulture.
- **The mirrored layout** (block 110): 25 test files moved and 5 split, so `src/<pkg>/a/b.py` is tested by
  `tests/a/test_b*.py`; `AGENTS.md` states the rule.
- **The gaps** (block 120):
  - Five crawler modules reached only from higher-level tests got direct tests.
  - `_COPY_MATCH_DECISIONS` is written out as literal SQL, with two tests of its dedup.
  - The merge logs each source catalog, merged or skipped.
  - The `sqlite3.connect` test no longer patches the module for the whole process, and a test's root logger
    leak is fixed.
- **`coverage_checks` and the mapping** (block 130): `unit-coverage-check` in `test`, after every package's
  suite, maps each `tests/**/test_*.py` to its module.
  - A test file that maps to none fails, unless its package lists it in
    `[tool.coverage_checks] tests_without_unit` with what it tests. An entry can be a directory
    (`tests/integration/`).
  - An entry naming no test file, a listed file that maps, or an entry without its reason fail too.
  - `own tests` joins the glossary. Ruff now targets Python 3.13 (class 1).
- **The measure** (block 135): `unit-coverage-check` reads coverage.py's analysis of each module, through
  `Coverage.json_report` restricted to the per-test contexts of its own tests, which every package's pytest now
  records (`--cov-context=test`).
  - A statement or branch outside any function (from the module's syntax tree, a one-line `def` counted as
    such) counts when any test ran it.
  - A data file without per-test branch coverage exits with how to record it.

## Decisions taken during Act

The operator's answers, from the block reports and the lead's notes:

- Block 40: ruff's `banned-api` cannot ban the written-out forms where `TID251` is ignored (every `tests/`
  tree, `packages/amule/`). The operator chose to have ast-grep refuse any import of `builtins` and drop the
  four `banned-api` entries: "Reco ok, ça me semble le plus robuste". The teammate added `__builtins__`, which
  passes `mypy --strict` with no import.
- Block 60: a result with a hash and a size but no usable name counts as skipped, so a drift renaming `name`
  is counted ("b").
- Block 80, after its pull request: a dead-code finding is deleted; the whitelist is a rare exit for a blind
  tool, and the tool's visibility is restored first. `AGENTS.md`'s wording is to be sharpened in block 140.
- Block 120, four answers:
  - the five client tests whose subject was the error mapping move to `test_errors.py` ("reco ok");
  - `_copy_journal` is written out as literal SQL ("c");
  - the dedup of `match_decisions` is pinned now rather than left to lot 3 ("a");
  - the `--into` skip becomes visible as a log line per source ("ok, c"), after the operator asked why a spy
    test was "internal".
- Size exemptions applied by the lead under the operator's 2026-10-13 rule for mechanical changes: block 10
  (lines, 544), block 60 (files, 21), block 110 (lines, 608). The operator was told each time and did not
  object. The spec's own exemption covers the files of blocks 10, 100 (61 files) and 110 (40); block 90 did
  not need its exemption (17 files).
- Block 130 passed both bounds whole (812 lines, 20 files) and is not mechanical, so the lead split it, the
  workflow's default: 130 keeps the mapping (426 lines, 14 files), 135 the measure (427 lines, 15 files).
- The closing block passed the files bound whole (20 files, 129 lines, before `BACKLOG.md`), so the lead split
  it the same way: 140 the documentation fixes and `BACKLOG.md` (3 files, 8 lines before `BACKLOG.md`), 150
  the code fixes, the spec's notes and this handoff, on top.

Each block's other departures, the ones a reviewer may weigh:

- Block 10: `TypeIs` for `TypeGuard`; `AGENTS.md`'s "VEX source guard" became "the VEX source claims check".
- Block 20: `_TOOLING_PACKAGES` gains `template_checks`; `packages/crawler/Dockerfile`'s comment no longer
  names the tooling packages.
- Block 30: the crawler gets `known_first_party` already, its tests being a package.
- Block 40: the rule refuses `__builtins__` too; L10's "setattr in a loop" was one through a variable.
- Block 50: the label "Coverage values:", two decimals rounded, every coverage token listed, fired or not.
- Block 60: 10 implementations of `SearchClient.search`, not 9 (the integration suite's fake); the DTO is
  named `SearchAnswer`; `docs/contributing/architecture.md`'s sequence diagram follows.
- Block 70: `open_reader` drops the `check_same_thread` argument, sqlite3's default being the check. The 25
  calls of `evaluate` are 20 in `test_engine.py`, 4 in `test_engine_properties.py` and 1 in the crawler.
- Block 80: `dead-code-check` is a `shell` task, since a `cmd` echoes the 1 KB name list into every log;
  `template_checks` declares `jinja2`; 100 template names, not 97.
- Block 90: `p2pwatch`'s `py.typed` waits for block 100; `known_first_party` in all five packages.
- Block 100: `packages/crawler_testing/**` joins `TID251`'s per-file ignores; the modules keep their paths
  inside the package; `_TOOLING_PACKAGES` lists every never-shipped member, tooling or not.
- Block 110: none in count; `test_disk_space.py` moved as the 25th, tests of `ShutilDiskSpace`.
- Block 120: `search_worker.py`'s gap was `SearchWorker.channels`; `merger.py` was also short of
  `_copy_journal`.
- Block 130:
  - `tests_without_unit` takes a directory entry, so criterion 2 subtracts nothing.
  - `unit-coverage-check` is a task of its own, a sequence over the packages, which `test` runs after every
    pytest rather than interleaved.
  - The summary counts the modules that have own tests.
- Block 135: a data file without per-test branch coverage exits with a message rather than a traceback.
- Block 140: the rule's example is generic (`BaseHTTPMiddleware(dispatch=...)`), since the webui's middleware
  is still a subclass at 140's tip; `docs/operate.md` also says a rise means the answers "ont peut-être
  changé de forme".
- Block 150: `matching_modules` for the review's `extended_modules`, `labels` for `items`, the harness's
  `module_paths` and the test parameter `listed_path`, so one name keeps one concept; the virtual loop's poll
  comes back as an `assert`, which refuses ready I/O rather than delivering it.

## Class 1 fixes

- Block 10: none. Block 20: two long dashes in `check_templates`' docstring.
- Block 30: the long dashes in the crawler's and matching's `[project]` descriptions.
- Blocks 40, 50, 60, 80: none.
- Block 70: the architecture page's sequence diagram (`evaluate_file(candidates)`, `list[MatchDecision]`),
  matching's `AGENTS.md` pipeline, a webui comment naming `quiesce`.
- Block 90: `.dockerignore`'s cache patterns at any depth (build context 68 MB to 21 MB, images unchanged).
- Block 100: the `compose_integration` marker help, a long dash in French prose, now English.
- Block 110: none.
- Block 120: `test_build_app_applies_log_level_when_observability_configured` restores the root logger's
  level.
- Block 130: root `[tool.ruff]` gains `target-version = "py313"`; without it ruff assumed 3.10 at the virtual
  root and sorted `tomllib` as third-party. With it, ruff reports nothing else on the tree.
- Blocks 135, 140 and 150: none.

## Spec corrections

Every `(Corrected ...)` in `agents/specs/2026-10-15-gate-tooling.md`, and the block that added it:

- Status, operator surfaces: the `merge` CLI's log line (block 120).
- L4: the entries' paths, the directory entry, the checks both ways (block 130).
- L5: `SearchWorker.channels`, `_copy_journal`, the merge log, the five moved tests, the two dedup tests
  (block 120).
- L9: a result without any usable name counts (block 60).
- L10: one `setattr` through a variable, not in a loop; the `builtins` import ban in place of `banned-api`
  (block 40, twice).
- L11: `dead-code-check` is a `shell` task (block 80); `unit-coverage-check` is a sequence `test` runs after
  every pytest, 1.4 s (block 130).
- L12: the root sources from block 100, not 80 (block 30); the false reason about a `test` group (after the
  spec review).
- Section 4's table: block 40's row (block 40); row 130 split, row 135 added (block 130).
- Section 4's bounds: blocks 10, 100, 110 and 90 under the exemption, after the spec review; block 10's lines
  (block 10's pull request); block 60's files (block 60); block 110's lines (block 110); the split (block 130).
- Order and transient states: the mapping before the measure, and block 130 measuring nothing (block 130).
- Acceptance 1: the `builtins` forms (block 40); the orphan in 130, the branch in 135 (block 130).
- Acceptance 2: N + M with nothing subtracted (block 130). Acceptance 4: block 135 is the last block before
  the closing one (block 130).
- Section 6: 100 template names, not 97 (block 80).

Beside them, three `(Corrected 2026-10-15: ...)` in the umbrella spec's measurements (the `pragma` count, the
unit coverage measure, vulture's findings), in the specs commit of block 10.

## Wrap counts

Counted with `gh run list --branch <b>` on each stack branch, 2026-10-15, after block 135's run and before
the closing blocks' push.

- **Fix-backs**: 2, both by the lead. Block 10's spec note (`720cc18`) and block 110's rewording
  (`fcfbe0a`). Blocks 140 and 150: none at writing.
- **Cascaded rebases**: 0.
- **Runs**: 16 on the 14 blocks before the closing one. One green run at the first pushed head for #231,
  #233 to #240 and #242 to #244. Two runs each, the first cancelled by the next push, then green, for #230
  (`d37858a` cancelled, `720cc18` green) and #241 (`ad1cbb9` cancelled, `fcfbe0a` green). Runs
  re-triggered: 2, against 16 blocks with the two closing ones.
- **Bodies the operator called unreadable**: none known at writing.

### Where the block reports and the lead's notes differ

- The lead's notes file L12's "from block 80" under block 100; the spec dates its correction at block 30,
  whose report flagged it.
- Block 110: the lead's notes count "1 extra run, 1 superseded run cancelled"; `gh run list` shows two runs
  in all, `ad1cbb9` cancelled and `fcfbe0a` green, so the extra run and the cancelled one are the same. The
  block report names `df05a09` and `fcfbe0a` as its green tips; `df05a09` never ran in CI.
- The lead's notes count 15 blocks and 17 runs, 15 green, before block 140; `gh run list` shows 14 blocks (10
  to 135) and 16 runs, 14 green and 2 cancelled.

## Holistic review

`holistic-review`, over `origin/main...origin/test/unit-coverage-measure` at `89e06a5`, report
`.reviews/gate-tooling-holistic.md` (gitignored): 0 critical, 2 major, 14 minor. Every decision and every
`(Corrected ...)` of the spec is implemented as written. Each finding, in the report's order, and its exit:

1. Major, `AGENTS.md`'s rule "No code only tests reach" made the whitelist the routine path. Fixed in 140:
   the rule and the whitelist's header say what the operator said after block 80, dead code is deleted and
   the whitelist is a rare exit once no rewrite can show the call.
2. Major, `_.dispatch` hid every unused `dispatch` of the seven scanned trees. Fixed in 150: the security
   headers are a function passed to `BaseHTTPMiddleware(dispatch=...)`, and the entry goes. Without the
   entry, the subclass gave `app.py:518: unused method 'dispatch'`; the rewrite passes with none.
3. Minor, block 100 deleted the fakes' strictness checks as lines the suite never runs. Fixed in 150: the
   bearer check, the login's `include_token` and the virtual loop's poll are `assert`s (Pitfalls).
4. Minor, `test_unit_coverage.py` set modules on a namespace through `__dict__`. Fixed in 150:
   a `dict[str, ModuleType]`. Its second half, the rule's blind forms (`__dict__`, `vars()`,
   `operator.attrgetter`, `__getattribute__`/`__setattr__`): waits for the operator.
5. Minor, the measure credits a body the process runs once to its first caller. Accepted limit, in
   `AGENTS.md`'s Gotchas (140) and the spec's section 6 (150); no instance exists.
6. Minor, `unit-coverage-check` run alone reads a stale or partial `.coverage`: waits for the operator.
7. Minor, `read_names`' unrequested `nodes.Getitem` branch. Fixed in 150: deleted with its three cases; the
   name list is identical, 100 names.
8. Minor, `test_app_console.py` imported three private helpers of another test module. Fixed in 150:
   `TickingMonotonicClock` joins `p2pwatch_testing.application.fakes`; each file keeps its own hash and
   runaway query.
9. Minor, names against the Naming rules in `coverage_checks`. Fixed in 150: `listed_path`, `coverage_data`,
   `labels`, and `matching_modules` rather than the review's `extended_modules`.
10. Minor, `_TOOLING_PACKAGES` held test support, and `TokenCoverage.coverage` reused the webui's word for a
    target's coverage. Fixed in 150: `_UNSHIPPED_PACKAGES`, `value_display`.
11. Minor, a dangling `# must not raise` closed `test_reader.py`. Fixed in 150.
12. Minor, four checks of block 130 were shown failing only at collection. Fixed in evidence (150): each
    broken in turn fails its own tests and no other (3, 2, 1 and 2 of 34), quoted in block 150's report.
13. Minor, `docs/operate.md` stated the skipped counter stays at zero, which no node measured. Fixed in 140: it
    "devrait rester à zéro", and a rise means the answers "ont peut-être changé de forme".
14. Minor, this handoff said no block but 60 ran the integration suites. Fixed in 150, under "Validated by CI
    only".
15. Minor, matching's `[project] description` was French. Fixed in 150.
16. Minor, `BACKLOG.md` keeps no pointer to lots 2 and 3: waits for the operator.

## Pitfalls

- **A new workspace member needs, beyond its `pyproject.toml`**:
  - its name in `vex_checks`' `_UNSHIPPED_PACKAGES` if no image ships it, a denylist whose test catches it;
  - its own `dev` group, `[tool.deptry]` and two `dependency-check` entries (deptry's second pass only warns
    without a `dev` group);
  - its `type-check` entry;
  - its `src` in ruff's `src` and in `[tool.vulture] paths` (but `p2pwatch_testing`);
  - its `pytest` entry in `test` and its `unit-coverage-check` entry;
  - `--cov-context=test` in its `addopts`;
  - `uv lock`.
- **Install proofs**: a host `uv sync --no-editable` reuses a member's cached wheel until its
  `pyproject.toml` changes, so an install check needs `--no-cache` (block 20). The image build does not
  inherit it.
- **deptry**: its default `exclude` holds `tests`, so `deptry src tests` scans `src` alone and passes. It must
  run from the workspace's venv, never `uvx`. Seeding a `pyproject.toml` needs `uv run --no-sync`, or uv
  relocks.
- **ast-grep** fails only on `severity: error`; a YAML `note:` holding `: ` must be quoted; it skips
  gitignored and hidden paths; it sees names, not bindings.
- **vulture**: a CLI `--ignore-names` replaces `[tool.vulture] ignore_names`, hence the whitelist file; a bare
  `vulture` reports the 27 view fields, `uv run poe dead-code-check` is the command.
- **mypy per package**: a `py.typed` package's errors show only in its own run; without the marker, an
  importer's run skips it (`import-untyped`, 61 and 77 errors measured).
- **Per-test contexts**:
  - pytest-cov records collection under the empty context, so a function called at import is owned by no
    test (block 120's `_copy_journal`).
  - `json_report`'s `contexts` are regular expressions searched in `<nodeid>|setup`, `|run`, `|teardown`,
    and an empty list means no filter.
  - A test patching `sqlite3.connect` for the process broke coverage's own writes (block 120).
  - They cost about 9 % of the crawler's run: 19.2 s to 21.0 s, measured at block 135.
  - A body the process runs once (a cached function, lazy module state, a session fixture) is credited to
    the first test that runs it, so its module's own tests would depend on test order (block 150).
- **A support-code guard that should never fire is an `assert`, not an `if`**: coverage.py counts no branch
  in an `assert`, so `p2pwatch_testing`'s 100 % keeps it, where block 100 deleted the `if`s. Without them, a
  client that dropped its bearer or forgot `include_token` failed one adapter test; with them, 57 and 73.
- **coverage.py counts no branch in a generator's `if`**: `read_names`' subscript filter stayed at 100 % with
  its three cases deleted, so no check could flag it (block 150).
- **coverage.py's JSON regions** file a one-line `def` (a `Protocol` stub) under the function, so L3's
  top-level rule walks the syntax tree itself. Block 120's throwaway `ast.walk` counted a nested `def` line as
  top-level, and a test now pins that case. A second `Coverage` started inside a pytest-cov run stacks over
  pytest-cov's collector and gives it back on `stop()`, which the measure's tests rely on.
- **Editing a member's `pyproject.toml`** makes the next `uv run` rebuild it; harmless.
- **Serena's blind spots met in this lot**, each closed by `git grep`, mypy or a restart:
  - `rename_symbol` does not follow strings (`monkeypatch.setattr(..., "GUARDS", ...)`), pytest fixtures,
    locals or docstrings (block 10).
  - pyright finds no structural implementation of a `Protocol`; mypy listed them (block 60).
  - `replace_symbol_body` replaces the whole symbol, so a partial body drops the rest (block 60).
  - `safe_delete_symbol` on a module-level constant leaves ` = <value>` behind (block 70).
  - pyright started before a new member's install reports `reportMissingImports` and empty references until
    its `pyright-langserver` processes are killed, after which Serena restarts it: done after blocks 100 and
    130. `pkill -f pyright-langserver` from a shell also matches that shell's own command line; kill by pid.
  - `rename_symbol` on `TokenCoverage.coverage` left the template's read, which the file page test's
    `StrictUndefined` failed on (block 150).
- **Same-named test files** now exist across directories (`test_main.py`, `test_errors.py`): a test module is
  `tests.<path>`, never a bare name.

## Left as is

- `packages/crawler/src/p2pwatch/domain/download/policy.py` "Guard order" and other prose uses of "guard",
  other concepts than the renamed one (block 10).
- `FakeAmuleApi`'s 404 for an unknown client ecid was not restored with the guards: `rows[0]` raises
  `IndexError`, already loud (block 150).
- The local branch `wip/unit-coverage-full` was deleted at block 135, which holds all of it.

## Validated by CI only

- The compose smoke, and `api_integration`, `download_integration` and `orchestration_integration` against
  the images just built, on amd64 and arm64, at every block (`build-and-verify` in
  `.github/workflows/validate.yml`). Block 60 also ran the three suites locally against
  `ghcr.io/mission-titar/p2pwatch-amule:main` (6 passed).
- Criterion 4, the images' installed packages, was checked locally by blocks 30, 100 and 135.
  - Block 135: `docker build --target python` of both Dockerfiles on `git archive` copies of `307de0b`
    (`main`) and `209940f` (block 135's code), the venv's `*.dist-info` listed. Crawler: 23 and 23. amule: 1
    and 1 (`p2pwatch_amule-0.0.0`). The crawler's frozen layer (`uv sync --frozen --no-install-workspace
    --package p2pwatch` on `uv.lock` and the root `pyproject.toml` alone): 21 and 21.
  - Each pair is identical, versions included.

## Not validated

- `grype-scan.yml` and `release.yml` on GitHub (cron and tag push): block 10 ran their commands locally
  against SBOMs syft generated from the `main` images. The daily scan keeps failing on the missing `latest`
  until the first p2pwatch release.
- The coverage values on the real node's catalogue (block 50).
- The skipped-results counter as scraped by Prometheus on a real node (block 60).
- The same-thread reader against the deployed node (block 70).
- The merge log on a real catalog; block 120 ran the CLI on scratch catalogs.

## Backlog

No entry of `BACKLOG.md` ships with this lot. The three block 10 added (mutation testing in the gate, the
template guard on Jinja's syntax tree, the fakes' contract tests) stay open. Entries for lots 2 and 3: wait for
the operator (finding 16).

## Next

- The operator reviews the stack, #230 to the closing block's pull request; the lead rebases it onto `main`
  (still at `307de0b` on 2026-10-15) and the operator merges.
- The lot changes the crawler image (the metric, the file page, the merge log, `_dev` gone), so Wrap (f)
  applies. The next release still waits for the copy before a migration that rewrites rows (`BACKLOG.md`).
- Then lot 2 of the umbrella spec (Serena and the language servers, U-D11), whose bench this lot's pitfalls
  above feed, and lot 3 (unique coverage, the pruning, mutmut), which reads `coverage_checks`' own tests.
