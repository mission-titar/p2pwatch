# Gate tooling, Serena and test quality

Status: umbrella spec of the three lots in D12, started in Discuss on 2026-10-14, approved by the operator;
a claim corrected after that approval says so. Each lot gets its own spec, which cites this one for the
decisions already taken and re-runs every measurement before acting on it.

## Why

The operator opened a tooling session with five axes: 100% branch coverage by unit tests; discouraging
tests that add no unique coverage (integration and e2e tests excepted); a dead-code detector; a checker of
unused and undeclared (transitive) dependencies; and a Serena that spares manual operations.

## Measurements (2026-10-14)

Taken on `main` at `307de0b`. The scripts live in the session scratchpad, which does not survive the
session: each lot's spec re-runs what it relies on, the `coverage_checks` package reproducing the first
four.

- **Coverage today**: every package's gate already requires 100% branch coverage, integration suites
  deselected and unmeasured. 20 `# pragma: no cover` in `src`: 10 `__main__` guards, 7 `assert_never`
  arms, 3 real exclusions. (Corrected 2026-10-15: 11 `__main__` guards, 7 arms, 2 real exclusions,
  `start_http_server` and `grype.py`'s `run`.)
- **Per-test contexts** (`pytest --cov-context=test`): crawler suite 19.9 s → 21.6 s, coverage data
  316 KB → 6.7 MB.
- **Unit coverage** under the mirror convention (D2): 22 modules have no test file named after them (their
  tests exist under other names, e.g. `tests/webui/test_webui_app.py` for `webui/composition/app.py`);
  12 modules are partly covered by their own tests only (e.g. 28 arcs of `mule_api/client.py`, 9 of
  `engine.py`). (Corrected 2026-10-15: a raw-arc measure; on lot 1's measure, statements and branches after
  the moves, five crawler modules are short and `client.py` and `engine.py` are fully covered by their own
  tests: `agents/specs/2026-10-15-gate-tooling.md`, L3 and L5.)
- **Unique coverage**, per test function (parametrize cases merged), within a module's own tests: 700 of
  954 functions cover no branch that another own test does not (crawler 516 of 667).
- **vulture** on `packages/*/src` alone, `--min-confidence 60`: 41 findings, 31 of them view fields that
  only Jinja templates read; 18 are reached only from tests (`is_terminal`, `quiesce`, `Engine.evaluate`,
  `skipped_results`). (Corrected 2026-10-15: vulture 2.16 gives 40 findings, 27 of them view fields only
  templates read, 5 library hooks, and 6 symbols reached only from tests; the 31 and 18 counted every unused
  variable and every test-only line.)
- **deptry** from each package directory: `src` clean in all five. Scanning tests too finds one real
  case: matching's tests import `yaml`, which matching does not declare (it is installed by the crawler).
- **Tests that break tooling**: `test_connection.py::test_open_closes_the_connection_on_a_non_persistence_error`
  patches `sqlite3.connect` process-wide, which breaks coverage.py's per-test contexts;
  `test_search_pacing.py::test_a_keyword_without_a_kad_target_is_logged_once` counts log records and
  depends on what ran before it; `test_disk_space` fails in 1 parallel run of 20;
  tests that find `deploy/` or `security/` through `Path(__file__).parents[N]`,
  and a vex_guards test that asserts a relative path, break when a tool runs the suite from a copy.
- **Language servers**: a bench of the five servers Serena 2.0 drives (pyright, basedpyright, ty, pyrefly,
  jedi) on the known blind spots and on the repository; its report moves to `agents/reference/` with lot 2.
  In short: no server renames a structural `Protocol` implementation or a `replace()` keyword; only
  pyrefly renames a nominal hierarchy (a base method and its overrides) completely, and it needs a
  `[tool.pyrefly]` section to resolve the workspace's imports under Serena; basedpyright alone finds a
  `Protocol`'s structural implementations; ty never reports import lines in references.

## Decisions

- **D1. Coverage is per unit.** Every branch of a module must be covered by that module's own unit tests;
  what a higher-level test covers in passing does not count, nor does a branch only an integration or e2e
  test reaches. Why: "with unit tests" is the operator's requirement, and incidental coverage hides an
  untested unit.
- **D2. A test names its unit by its path**, mirroring `src`: `src/<pkg>/a/b.py` is covered by
  `tests/a/test_b*.py`. Misplaced test files are renamed or moved. Where keeping a coherent group of code
  would mean splitting a module, the split is discussed with the operator case by case. Why: no
  annotation to write or keep true, and a module's tests are found at once; an explicit marker per test
  module (about 140) can lie.
- **D3. Every unit test function has unique coverage**: at least one branch of its unit that no other test
  of that unit covers, parametrize cases counting as one function. A test that checks what coverage cannot
  see carries `@pytest.mark.beyond_coverage("<what it checks>")`, the reason mandatory; a marked test is
  left out of the uniqueness computation (it can neither be judged redundant nor make another test
  redundant) and still counts for D1. The existing stock is processed before the gate turns on, with no
  baseline file. Why: the operator refused both deferring the stock to a tolerated list and a report the
  gate does not enforce; the marker's name says why the test stays.
- **D4. The decision method for a test without unique coverage**, applied module by module (removing a
  test gives unique coverage back to its neighbours, so decisions within a module depend on each other),
  comparing the test with the tests that already cover its branches:

  | Situation | Decision |
  |---|---|
  | It checks nothing its covering tests do not | delete |
  | Same scenario as a covering test, another assertion | merge: the assertion joins that test |
  | Same path, other data (bounds, equivalence classes) | parametrize into one test function |
  | The covering test is a broad one replaying several behaviours | split the broad test into focused tests |
  | It checks a property coverage cannot see and that does not merge | keep, with `beyond_coverage` |

  Merges and parametrizations add assertions or data, never a call into the tested code; the pieces of a
  split go through the same judgment. Each round applies the decisions, re-measures, and re-judges only the
  tests whose status changed. Why it converges: a split lowers the number of broad tests, every other
  decision lowers the number of tests without unique coverage without creating a broad one, and every
  such test always has an exit (the marker last). A module still unstable after 3 rounds goes to the
  operator as a defect class 2 question, against an error in the reasoning or in applying it.
- **D5. Triage by inexpensive agents**: Sonnet agents apply D4 per group of modules and return decision
  tables that are not versioned; the lead samples them, the operator validates the method, the totals and
  examples rather than every row; Opus teammates apply the decisions in blocks. This departs from
  `agents/workflow.md` ("every agent the lead dispatches runs on Opus"), which lot 3's spec states. Why:
  the operator asked for inexpensive help on a large mechanical judgment that the gate re-checks.
- **D6. vulture runs on `src` without the tests**, at `--min-confidence 60`: code that only tests reach is
  dead, and is deleted with its tests. This runs before the test pruning. Why: such code serves nothing in
  production and its tests only check themselves; pruning after it avoids judging tests of dead code.
- **D7. Names read by templates are extracted from the templates** and passed to vulture; a hand-written
  whitelist holds only library hooks (`optionxform`, `dispatch`, `row_factory`, `should_exit`), each with
  its reason. Why: a static list rots and keeps a field no template reads any more.
- **D8. deptry checks `src` and tests, per package**: each package declares its own test dependencies in
  its `[dependency-groups]`, which deptry reads as development dependencies; the root keeps only the
  workspace tools (ruff, mypy, poe, sqlfluff, zensical, and the like: lot 1's L12 lists them). deptry then also checks that `src` imports no
  test-only dependency. Why: the undeclared transitive case the operator wants caught exists today in
  tests (`yaml` in matching), and each package then describes itself, like its gate.
- **D9. Two new tooling packages**, never shipped and held to 100% coverage like the others:
  `coverage_checks` (D1 and D3) and `template_checks` (logic-free templates, and the names templates read
  for D7). `check_templates` leaves `p2pwatch.webui._dev`, the only underscore subpackage, which dates from
  when the webui was its own package and ships in the crawler image today
  (`uv sync --no-editable --package p2pwatch`). Why: a newcomer reads what each package checks from its
  name, where one abstract name (`code_guards`) would not say it.
- **D10. `vex_guards` becomes `vex_checks`**, and its `Guard` becomes `Premise` (`GUARDS` becomes
  `PREMISES`), the word its own docstring uses for "the falsifiable premise each claim rests on"; the whole
  family follows, one concept keeping one name (`SourceGuard` and `ImageGuard` become `SourcePremise` and
  `ImagePremise`, `is_source_guard`, `evaluate_source_guards` and their image twins likewise, the test names
  and the prose in the package, `SECURITY.md` and the workflows). (Corrected 2026-10-15, after the spec
  review: `Guard` alone would have left the concept under two names.) A
  mechanical rename over 32 files outside `agents/`, which takes the one-line exemption if it passes a
  block's bounds. Why: consistent with D9's names, and more telling.
- **D11. Serena: the bench first, then code adaptations only for the blind spots the chosen server keeps.**
  The blind spots that remain go to `AGENTS.md`'s Gotchas, which every agent and teammate already reads;
  `.serena/project.yml` is versioned as soon as it names a server other than the default. Why: the bench
  tells which adaptations are worth their cost; a Serena-only prompt would miss sessions that do not
  activate Serena; without a versioned config every clone falls back to pyright.
- **D12. Three lots, in this order, each with its spec and stack**: (1) gate tooling: D6 to D10 and D17,
  deptry, the tests moved to D2's layout, D1's check and the gaps it finds; (2) Serena and the language servers;
  (3) test quality: D3 to D5. Why: one stack of 25 to 35 pull requests means endless rebase cascades and a
  review no one can do in one sitting; Serena comes before the pruning, whose many symbol deletions and
  renames benefit from a reliable tool.
- **D13. mutmut is a tool, not yet a gate**: a dev dependency with a local `poe` task, used by lot 3 as a
  before/after proof that pruning loses no detected mutant. Mutation testing in the gate goes to
  `BACKLOG.md`, added with this spec's first commit, as the impact-scoped design below. Why: a cold
  full run takes about 16 min for the crawler on 4 fast cores and more on a GitHub runner; the operator
  refuses both a nightly full run and a CI matrix; no tool's incremental cache is correct; and the three
  lots already make enough work.

  The bench (`agents/reference/`, with lot 3), 2026-10-14/15, 4 cores: mutmut 3.8.0 is the only tool both
  exhaustive and fast enough (crawler 7836 mutants in 974 s, 895 survived; matching 1059 in 82 s, 98);
  pytest-gremlins makes 8 times fewer mutants, without the string, None and argument mutations behind
  most survivors; cosmic-ray has no test selection (crawler extrapolated to 2 h 32). mutmut's cache is
  wrong when a test is deleted, when a caller changes, and for files other than `.py` (stale copies under
  `mutants/`), all three located in its source. `build_app` alone is 1006 mutants and 34% of the crawler's
  time; the golden corpus is 80% of matching's for 3 mutants.

  The design for the backlog: run mutmut cold on the pull request's **impact set** only, computed from the
  per-test coverage D1 and D3 already produce: the functions changed, those executed by the tests the pull
  request changes or deletes, and those executed by tests that run changed code; a full run when the
  lockfile, mutmut's configuration or a data file read by tests changes (or a per-test record of the files
  each test opens). A mutant's verdict depends only on its function, the tests that run it, the code they
  run and what they read, so the scoped run is correct by construction once `main` has no survivor; it
  does not rely on mutmut's cache, only on its selection of mutants by name. The existing survivors (about
  1090, 691 for the crawler once the mutants mypy rejects count as caught) go with that entry: the gate
  only makes sense from zero, and pruning does not need them gone to be safe (D14).
- **D14. What makes a pruning block safe**, on top of D1's and D3's checks:
  - **A mutation proof**: no mutant detected before the block goes undetected after it; mutants that
    survived before do not matter, since a check that did not exist cannot be lost. mutmut runs cold,
    never from its cache (wrong precisely when a test is deleted), over the whole package (a test of one
    module can be the only one detecting a fault in a domain type it runs through), with unit tests only
    (D1; the golden corpus would otherwise mask a lost unit test). A pruning block touches tests only, so
    the mutant set is identical and the comparison is mutant by mutant; a block's "after" is the next
    block's "before".
  - **Stable verdicts first**: the three tests named under Measurements (`sqlite3.connect`, the log count,
    `test_disk_space`, which fails in 1 parallel run of 20) are fixed and the repository root is found
    without `parents[N]` before the first measurement, or a flipping verdict reads as a loss.
  - **Mutation's blind spot**: mutmut mutates Python only, so a test whose subject is a template, a SQL
    migration or `deploy/matcher.yml` is left out of automatic pruning and judged with the operator.

  Why: coverage proves no branch is lost but not that no check is; the proof also catches the triage
  agents' wrong "delete" decisions (D5).
- **D15. Lot 3's pruning blocks take the size exemption**: one block per package, two or three for the
  crawler by subtree; each pull request carries its decision table and its D14 proof, which the review
  reads instead of every deleted line. Why: decisions are independent between modules, so a package is a
  coherent unit; each proof costs one cold run of the package, which blocks under 500 lines (10 to 20)
  would multiply without making the review more useful.
- **D16. The poe tasks**: `dead-code-check` (D6), `dependency-check` (D8), `unit-coverage-check` (D1),
  `unique-coverage-check` (D3), `template-check` (unchanged, D9), `code-pattern-check` (D17, added
  2026-10-15) and `mutation-check` (D13, outside `check`). Why: the existing `<subject>-check` form; no abbreviation outside the glossary (`deps`); that a
  task is not part of the gate is said by its absence from `check`, not by breaking the name's form.
- **D17. No dynamic attribute access**: `getattr`, `setattr`, `hasattr` and `delattr` are banned in `src` and
  tests, enforced by an ast-grep rule (`no-dynamic-attribute`, PyPI `ast-grep-cli`) run by a poe task in
  `lint-all`; an exception carries `# ast-grep-ignore: no-dynamic-attribute` and its reason. The five uses
  today go: `matchers.py`'s `getattr` on a policy-named field becomes a typed accessor table replacing
  `ATTR_NAMES`, `reader.py`'s read of a `threading.local` becomes a typed `threading.local` subclass, and the
  three in tests are rewritten. Why: dynamic access hides reads from mypy, vulture and the language server
  (`FileCandidate.size_mib` looked dead to vulture); ruff 0.16.9 cannot ban a builtin (`banned-api` matches
  only `builtins.getattr(...)` written out; B009 and B010 cover constant names only), and ast-grep adds
  structural rules without duplicating ruff, where pylint would duplicate it almost entirely (the operator,
  2026-10-15).

## Open

- **Lot 2's choices**: which language server; `Protocol` ports turned into ABCs or explicitly inherited;
  whether ty replaces mypy (the operator leans towards ABCs and ty; the bench shows ty does not propagate
  a rename to overrides, which only pyrefly does).

## Adjacent backlog items

None: no `BACKLOG.md` entry concerns the gate's tooling, Serena or the test suite.
