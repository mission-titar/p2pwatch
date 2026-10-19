# Handoff: hexagonal rings, lot 1b of the hexagonal architecture umbrella

Drafted by block 85 from the lot's block reports (#266, #267, #269 to #279), corrected by the closing block 90
from the reports of blocks 86 to 88 (#280 to #282) and the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-18-hexagonal-foundations.md`, section "Lot 1b", approved by the operator
on 2026-10-18 with lot 1a, and re-measured on 2026-10-19 by a dry run of the whole lot on `013252c`
(`.reviews/lot1b-measure.md`, gitignored: 13 contradictions, each a `(Corrected 2026-10-19: ...)` in the spec,
committed by block 10). The lot carries out the second half of lot 1 of the umbrella spec
`agents/specs/2026-10-18-hexagonal-architecture.md`.

Seventeen blocks, one stack cut from `main` at `013252c` (lot 1a merged). Blocks 86 to 90 are the closing block,
split in four for the file bound:

| Block | Pull request | Branch |
|---|---|---|
| 10 | #266 | `refactor/matching-domain-ring` |
| 20 | #267 | `refactor/crawler-ports-adapters-rings` |
| 25 | #269 | `test/webui-fixtures-shared` |
| 30 | #270 | `refactor/webui-rings` |
| 40 | #271 | `refactor/amule-rings` |
| 50 | #272 | `feat/amule-entry-points` |
| 55 | #273 | `refactor/amule-bump-repo-port` |
| 60 | #274 | `refactor/tooling-rings` |
| 70 | #275 | `feat/vex-checks-entry-points` |
| 73 | #276 | `feat/template-coverage-entry-points` |
| 77 | #277 | `feat/amule-bump-entry-point` |
| 80 | #278 | `feat/architecture-gate` |
| 85 | #279 | `feat/architecture-gate-all-hexagons` |
| 86 | #280 | `fix/architecture-gate-holes` |
| 87 | #281 | `refactor/rings-leftover-moves` |
| 88 | #282 | `chore/hexagonal-rings-residue` |
| 90 | closing, last quarter | `docs/hexagonal-rings-wrap` |

Nothing of the stack is merged. The lot changes what both images run (the aMule container's entrypoint and s6
script, logger names in both), so Wrap (f) proposes a release, but not before the backlog's "A copy before a
migration that rewrites rows" ships (spec, section "Backlog").

**One open point**: block 86's dependency test also allows `p2pwatch-testing` on `p2pwatch`, beyond the two
edges the operator named for exit (a). The lead has asked the operator; the answer is pending.

## What was built

- **`catalog_matching` in its domain ring** (block 10): its ten modules under `catalog_matching/domain/`, their
  tests under `tests/domain/`. The golden corpus test and its fixtures stay at the tests root.
- **The crawler's ports and adapters by side** (block 20): `ports/*.py` to `ports/driven/`, `crawler_control.py`
  to `ports/driving/`; every adapter but lot 1a's driving ones to `adapters/driven/`.
- **The webui's fixtures in `p2pwatch_testing`** (block 25):
  `p2pwatch_testing.adapters.persistence_sqlite.migrated_databases`, registered once by `pytest_plugins` in the
  crawler's `tests/conftest.py`. The connection closer, renamed `close_test_connections`, is no longer autouse:
  each of the twelve webui test modules asks for it with `pytestmark` (seven since block 88). `--setup-plan`
  counts 326 setups before and after.
- **The webui as a driving adapter** (block 30): `adapters/driving/webui/` (Starlette routes, uvicorn thread,
  views, formatting, query-string parsing, templates, static files); the three SQLite readers to
  `adapters/driven/persistence_sqlite/`; `matching_read.py` to `application/`; `coverage.py` and
  `CoverageStatus` to `domain/coverage.py`.
- **`p2pwatch_amule` in its rings** (block 40): `conf` in `domain/`; `boot`, `port_sync` and `settings` in
  `adapters/driving/`, as plain modules; `gluetun` in `adapters/driven/`. Block 87 moves `settings` to
  `adapters/driven/`.
- **`python -m p2pwatch_amule boot` and `port-sync`** (block 50): the root `__main__.py` hands the two `main`
  functions to `ArgparseCommandLine` as callables, so the command line imports no other adapter. It sets up
  logging for both. The entrypoint and the s6 `run` call the subcommands.
- **`amule_bump`'s port** (block 55): `github.py` split into the port `RepoReader` (an ABC, renamed at the
  operator's answer), `domain/upstream.py`, `domain/bump_error.py` and the adapter `GitHubRepoReader`; the
  test double `FakeRepoReader(RepoReader)`.
- **The four tooling packages in their rings** (block 60): see the table of #274. `amule_bump`'s `body` and
  `release` are in `application/`, since they call the port; its old `__main__.py` moved with `git mv` to
  `adapters/driving/bump.py`.
- **`vex_checks`' four subcommands** (block 70): `image-claims`, `stale-claims`, `source-claims`,
  `claim-coverage`. The command line owns every option and refuses `--format sarif` without `--output` (exit
  2); each check takes typed arguments (`sarif_output: Path | None`). The root `__main__.py` builds the stale
  check's `SubprocessGrypeRunner`. Two poe tasks, `grype-scan.yml`, `release.yml` and `SECURITY.md` follow.
- **`template_checks`' `logic-free` and `read-names`, `coverage_checks`' `unit-coverage`** (block 73): the
  checks return their exit code instead of calling `sys.exit`; the nine poe lines follow.
- **`python -m amule_bump bump`** (block 77): the command line owns `--dockerfile`, `--body-file`, `--dry-run`;
  the root `__main__.py` builds `GitHubRepoReader` from `GH_TOKEN` and reads `GITHUB_OUTPUT`, which removes
  the bump's edge to the GitHub adapter.
- **`architecture-check` over the `p2pwatch` hexagon** (block 80): tach 0.35.3, one `tach.toml` at the root, 45
  modules, five layers, `layers_explicit_depends_on`, `exact`, `root_module = "forbid"`,
  `forbid_circular_dependencies`, `ignore_type_checking_imports = false`; twelve deprecated edges around the
  webui, each naming lot 2. The three readers and `webui.views` are tach modules of their own, which breaks the
  webui's cycle.
- **Every hexagon checked, and the core's imports** (block 85):
  - tach over the five other hexagons: 36 more modules (81 in all), 19 more deprecated edges (31 in all:
    `vex_checks` 13, `p2pwatch_amule` 3, `amule_bump` 2, `coverage_checks` 1), each naming lot 3;
  - `architecture-check` runs `tach check`, then `tach check-external`, which holds every import across
    distributions to its package's `pyproject.toml` (Pitfalls);
  - four ast-grep rules in `code-pattern-check`: `domain-imports`, `ports-imports` and `application-imports`
    (one list per ring, from the imports each ring holds, `logging` in `application/`'s until lot 2), and
    `core-import-names` (`asyncio`, `uuid` and `io` by name, `pathlib` by `PurePath`, no `from asyncio import`);
    a shared matcher in `ast-grep-utils/imported-module.yml`; each rule tested by `ast-grep test` in
    `ast-grep-tests/`, run before the scan;
  - `AGENTS.md`'s architecture rules (the six hexagons, the rings read from the path, the dependency rules, no
    I/O in the core, every module declared), and the passages the lot made stale.
- **The gate's holes closed** (block 86, holistic findings):
  - `core-import-names` refuses `import asyncio`, `uuid` or `io` under an alias, as it already did `pathlib`;
  - `core-builtins`: no call of `open`, `print`, `input`, `__import__`, `exec` or `eval` in a core ring;
  - `domain-configparser`: `configparser` refused in every domain but `p2pwatch_amule`'s, by `ignores`;
  - `packages/crawler/tests/test_workspace_dependencies.py` reads every `packages/*/pyproject.toml` and holds the
    workspace's internal dependencies to `p2pwatch` on `catalog-matching` and on `p2pwatch-testing` (`dev`),
    and `p2pwatch-testing` on `p2pwatch` (the open point above), so a declared cross-hexagon dependency fails
    the gate;
  - the ring rules' messages no longer claim "its own hexagon"; `AGENTS.md`'s package boundary invariant is
    rewritten from the hexagon rule, and the core's rule says what the checks see.
- **Two modules where they stay** (block 87): port-sync's `settings` to `adapters/driven/`, since lot 3 gives it
  a driven port; `p2pwatch_testing/merge/helpers.py` to `p2pwatch_testing/adapters/persistence_sqlite/`, a spec
  row no earlier block carried out, and `merge/` deleted.
- **The review's residue** (block 88): the closer off the five test modules that open no connection,
  `SubprocessGrypeRunner.run` tested by its own tests and its pragma gone, the published rings diagram's arrow
  reversed (`ports --> dom`), comments and paragraphs that drifted.

## What an operator sees change

- **Logger names**, written in `docs/migration-4x.md` where an operator filters on them:
  - `p2pwatch.adapters.mule_api.client`, `p2pwatch.adapters.persistence_sqlite.connection` and
    `...sqlite_catalog_copier` gain `.driven` (block 20);
  - "webui serving on": `p2pwatch.adapters.driving.webui.uvicorn_server_thread` (block 30);
  - port-sync: `p2pwatch_amule.adapters.driving.port_sync`, and its gluetun calls
    `p2pwatch_amule.adapters.driven.gluetun`, no longer a child of port-sync's (block 40);
  - `p2pwatch.observability`, the dispatcher's, spells no module and stays.
- **Commands inside the images**: the aMule container runs `python -m p2pwatch_amule boot` and `port-sync`
  (block 50). Nothing an operator configures changes.
- **Contributor commands**: `python -m vex_checks <check>` (block 70), `python -m template_checks <check>`,
  `python -m coverage_checks unit-coverage` (block 73), `python -m amule_bump bump` (block 77). The pre-lot
  module paths fail loudly: `python -m vex_checks.check_image_claims`, `template_checks.check_templates`,
  `coverage_checks.unit_coverage`, `p2pwatch_amule.boot` and `p2pwatch_amule.port_sync` exit 1 (no module),
  the bare `python -m amule_bump` exits 2 (checked on 2026-10-19 at `e78aa9f`). Only the in-ring paths that
  existed inside the stack exit 0 doing nothing (Pitfalls).

## Acceptance

6. Block 85: `python -m <package> --help` lists `{crawl,validate-config,merge}`, `{boot,port-sync}`,
   `{image-claims,stale-claims,source-claims,claim-coverage}`, `{logic-free,read-names}`, `{unit-coverage}` and
   `{bump}`. The bare invocation exits 2 with a usage line (blocks 50, 77).
7. Each refusal seen failing, then reverted:
   - block 80, the `p2pwatch` part: a domain importing `application/`, an adapter importing another, an
     undeclared module (#278's report quotes each);
   - block 85, `uv run poe architecture-check`, exit 1:
     - `p2pwatch_amule` importing `p2pwatch` (`gluetun.py`):
       `[FAIL] packages/amule/src/p2pwatch_amule/adapters/driven/gluetun.py:3: Dependency 'p2pwatch' is not
       declared in package 'p2pwatch-amule'.` Without `check-external`, `tach check` passed it, exit 0;
     - a domain importing `application/` (`amule_bump`):
       `Layer 'domain' ('amule_bump.domain') is lower than layer 'application' ('amule_bump.application').`;
     - an adapter importing another (`vex_checks`' `sarif` to `grype`):
       `Module 'vex_checks.adapters.driven.sarif' cannot depend on 'vex_checks.adapters.driven.grype'.`;
     - an undeclared new module (`coverage_checks/adapters/driven/stray.py`), imported:
       `Module 'coverage_checks.adapters.driving.unit_coverage' cannot depend on '<root>'.`;
   - block 85, `ast-grep scan`: `import sqlite3` in `p2pwatch/domain/file_key.py` fails, exit 1,
     `error[domain-imports]: A domain imports only the pure standard library on this list, ...`; `import
     dataclasses` there passes, exit 0. `import shutil` fails in `amule_bump`'s port and application and in
     `coverage_checks`' domain, and passes in `p2pwatch_testing/application/fakes.py`, which the rules exclude;
   - block 86: the three aliased imports, `open("/etc/passwd")` in `application/`, `import configparser` in
     `p2pwatch/domain/`, and `amule_bump` declaring `p2pwatch`, each quoted in #280's report.
8. The gate is green at every block's tip. CI ran once per pull request from #266 to #282, attempt 1, green at
   each head, `build-and-verify` on amd64 and arm64 included: blocks 20 (`39175192684`), 50 (`39176957049`),
   70 (`39178676426`) and 85 (`39181471476`) among them. #280 to #282 likewise (`39184916658`, `39184921818`,
   `39184927457`).
9. Blocks 30 and 85: the `git diff -M100%` command prints nothing.

## Departures from the spec

- **Sizes past the spec's row**, all under both bounds but the exempted moves: 50 (156 lines, 13 files; row 116,
  16), 55 (127, 19; row 42, 14, grown by the rename), 70 (498, 16; row 200), 73 (367, 19; row 264, 14), 77
  (238, 10; row 133, 7): the command lines own every option, with their tests. Block 85: 405 lines, 14 files
  (row 430, 13). The closing block, unmeasured in the spec: 86 (98, 12), 87 (23, 10), 88 (66, 12).
- **Size exemptions**, mechanical moves as the spec states: blocks 10 (124, 65), 20 (354, 187), 30 (182, 52), 40
  (44, 30), 60 (121, 80).
- **`RepoReader`**, not `Repo` (block 55, the operator's answer), hence `github_repo_reader` (block 60).
- **The command lines receive the checks and entry points as callables** from the root `__main__.py` (blocks 50,
  70, 73), so no command line imports another adapter.
- **The stale check's default runner is gone** (block 70): the root `__main__.py` builds it.
- **The checks return an exit code** rather than exiting (block 73).
- **`amule_bump` has two deprecated edges**, not the dry run's three (block 77).
- **`ignore_type_checking_imports = false`** (block 80), beyond D15's flags: a `TYPE_CHECKING` import of an
  adapter into the domain passes under tach's default.
- **`tach check-external` in place of `visibility`** (block 85): `tach check` never sees an import across
  distributions, so `visibility` would only check the configuration. `check-external` refuses only an
  undeclared import, as deptry already did, so block 86's test holds the declarations themselves.
- **ast-grep's lists are one per ring** (block 85): `io`, `ast`, `difflib`, `textwrap` and `rapidfuzz` sit in
  their ring's list for every hexagon; `io` is reachable by `StringIO` only. `configparser`, which reads files,
  is held to `p2pwatch_amule`'s domain by its own rule (block 86), the appendix's stated reason corrected.
- **The dependency test also allows `p2pwatch-testing` on `p2pwatch`** (block 86): that package's runtime
  dependency today, without which the test fails on the current tree. Pending the operator's answer.
- **`core-builtins` also refuses `exec` and `eval`** (block 86), beyond the review's four.
- **The fake-`grype` case was copied, not moved** (block 88): `tests/test_main.py` keeps its stale-claims wiring
  test against the real runner.

## Spec corrections

- Block 10: the dry run's corrections, each `(Corrected 2026-10-19: ...)` in lot 1b's section.
- Block 85: "The check" and the appendix's ast-grep lists, in the foundations spec; D6 and D15 in the umbrella
  (`check-external` for `visibility`).
- Block 86: "The check" (the dependency test), the appendix's reason for one list per ring, the dangling table
  header deleted, 31 exceptions and acceptance 7's block 85 marked, in the foundations spec; D3, D15 and D18's
  lot 3 (the naming finding) in the umbrella.
- Block 87: the `p2pwatch_amule` row (`settings` driven).
- Block 90: the block table's rows 86, 87 and 88.

## Tests pruned or moved

- Block 30: `tests/domain/test_coverage.py` follows `coverage.py`.
- Block 70: the monkeypatch test of the stale check's default runner is deleted; the checks' `argv` call sites
  are rewritten or deleted.
- Block 73: the tests of the two hand-written usage lines are deleted, argparse's required positional tested in
  the command lines' tests instead.
- Block 77: the default reader's test becomes `tests/test_main.py`'s wiring test; the default Dockerfile test
  becomes the command line's defaults test.
- Block 88: `tests/adapters/driving/webui/test_init.py` deleted (it asserted only the package's `__name__`, and
  the empty `__init__.py` holds no statement to cover); the fake-`grype` case copied into `test_grype.py`.

## Class 1 fixes

- Block 10: the em dashes of `format.py`'s docstring.
- Block 20: `docs/contributing/architecture.md`'s code map named the deleted `ports/mule_client.py`.
- Block 25: the moved module's French banner; the closer's docstring.
- Block 30: the em dash of `ed2k_link.py`'s docstring.
- Block 40: `amule_bump`'s checklist named `p2pwatch_amule.boot`; it names `p2pwatch_amule.domain.conf`, where
  the defaults live.
- Block 55: `AGENTS.md`'s `FakeRepo` example.
- Block 85: `docs/contributing/testing.md`'s `lint` job, which named neither tach nor the allowlists.
- Block 88: `vulture_whitelist.py`'s `reader.py` path, short like the `uvicorn_server_thread.py` one.
- Blocks 50, 60, 70, 73, 77, 80, 86, 87: none.

## Class 2 questions

- Block 55: `Repo` breaks the port naming rule. Operator's answer: "Renommer".
- Every other block: none. The holistic review's two questions are under "Holistic review".

## Pitfalls

- **`tach check` never sees an import across distributions**, each `src` with its `pyproject.toml` being a
  package of its own: `p2pwatch_amule` importing `p2pwatch` passes it, and so does every crawler import of
  `catalog_matching`. `visibility` then only refuses a declared edge, which `exact` already fails as unused.
  Block 80's "a cross-hexagon import is already an undeclared edge" did not hold. `tach check-external` and
  deptry both refuse the undeclared import; neither refuses a declared one, which the dependency test does.
- **The deprecated edges print 90 `[WARN]` lines** in every gate run, by design (counted on 2026-10-19 at
  `e78aa9f`, `tach check`).
- **ast-grep's `field` on a relational rule matches the first child of that field only**: `inside: { kind:
  import_statement, field: name }` misses `sqlite3` in `import dataclasses, sqlite3`. The shared matcher tests
  the direct parent instead, and a rule test holds that case.
- **`ast-grep test --skip-snapshot-tests` still checks each case's verdict** (a `[Missing]` fails it); it only
  skips the snapshots of the messages, which would be generated files.
- **`ast-grep test` silently passes a test file whose rule id does not exist** (block 86): a new rule's test is
  watched failing only once the rule file exists, stubbed with `regex: ^$`.
- **The ast-grep rules exclude `packages/crawler_testing/`**, whose `application/` holds fakes.
- **The core's rules see imports and six builtins only**: an allowed module's methods that do I/O pass (block
  86, `AGENTS.md`'s core rule).
- **The in-ring module paths exit 0 doing nothing**, an accepted limit (holistic review):
  `vex_checks.adapters.driving.check_image_claims`, `template_checks.adapters.driving.check_templates`,
  `coverage_checks.adapters.driving.unit_coverage`, `amule_bump.adapters.driving.bump`,
  `p2pwatch_amule.adapters.driving.boot` and `.port_sync`, since their `__main__` guards went (checked on
  2026-10-19 at `e78aa9f`). No caller is left, but a hand-typed release gate on such a path would pass
  silently: call the subcommand.
- **A same-size `sed` swap undone within a second leaves stale bytecode** (`.pyc` keyed on mtime in seconds and
  size): clear `__pycache__` (block 50).
- **git pairs moved empty `__init__.py` files arbitrarily** (block 20); harmless.
- **Port-sync's logger is a string**, since `__name__` is `__main__` under `-m` (block 40).
- **`test_grype.py` and `test_main.py` run `SubprocessGrypeRunner` against a fake `grype`** shell script first
  on `PATH`, so both need `/bin/sh` (blocks 70, 88).
- **Migration `0004`'s comment names the old `webui/adapters/catalog_read.py`**: left, since no migration's
  content may change (block 30).

## Not validated

- `release.yml`, `grype-scan.yml` and `amule-bump.yml` on Actions: tag-triggered or scheduled, their new command
  lines checked by local runs only (blocks 60, 70, 77).
- The integration suites were collected, not run, locally (blocks 10, 20); CI's `build-and-verify` runs the smoke
  on both architectures in every run.
- The image built from block 50's branch, locally: the published `p2pwatch-amule:main` was run with the branch's
  package and scripts mounted; CI built the real one.

## Holistic review

By `lot1b-holistic` over `git diff origin/main...origin/feat/architecture-gate-all-hexagons`
(`.reviews/hexagonal-rings-holistic.md`, gitignored): 0 critical, 2 major, 14 minor. Every finding was fixed in
the lot but 12 (lot 3) and 15 (an accepted limit).

1. MAJOR, an aliased import of `asyncio`, `uuid` or `io` bypassing `core-import-names`: fixed (block 86).
2. MAJOR, the spec row `p2pwatch_testing/merge/helpers.py` dropped: fixed (block 87), moved, `merge/` deleted.
3. Hexagon isolation with no check of its own, `check-external` duplicating deptry: fixed (block 86) with the
   operator's choice (a), "Reco ok": the workspace dependency test. Its third edge is the open point.
4. The ring rules' messages claiming "its own hexagon": fixed (block 86), reworded.
5. `AGENTS.md`'s "no I/O in the core" stating more than the gate checks: fixed (block 86), `core-builtins`.
6. `configparser` allowed in every domain: fixed (block 86), `domain-configparser`, the spec's reason corrected.
7. Port-sync's settings on the driving side: fixed (block 87), moved to `adapters/driven/`.
8. The published diagram's `dom --> ports`: fixed (block 88); "protocols" and "structurellement" left to lot 3,
   as D19 says.
9. `AGENTS.md`'s package boundary invariant untouched: fixed (block 86), rewritten from the hexagon rule.
10. This handoff's three misstated facts: fixed (block 90), the old paths' exits, #279, CI on #279.
11. Spec hygiene: fixed (block 86), the dangling header, 31 exceptions, acceptance 7's block 85.
12. One concept under several names, the called functions still `main`: lot 3, the operator's words "B ok
    puisqu'on les traite en lot 3"; a marked line in D18's lot 3 of the umbrella, no name changed.
13. The connection closer on five modules that open none: fixed (block 88), `test_init.py` deleted, the
    docstring cut to its trap.
14. `SubprocessGrypeRunner.run`'s stale pragma: fixed (block 88).
15. The in-ring module paths exiting 0: an accepted limit, written in the pitfalls.
16. Comment drift: fixed (block 88), `tach.toml:1`'s decision ids in block 87.

## Wrap counts

From `gh run list --branch <branch>` and `git rev-parse origin/<branch>` on 2026-10-19, before block 90 was
pushed.

- **Runs**: one per pull request from #266 to #282, sixteen, each at its branch's current head, attempt 1,
  green. #267 also had one run cancelled by a second push (`5e75ec0`, then `f1ffbfe`), before its report.
- **Fix-backs**: none.
- **Cascaded rebases**: none: no pushed head moved.
- **Splits**: the closing block in four (86, 87, 88, 90), beyond the re-measured table. **Exemptions**: five,
  blocks 10, 20, 30, 40, 60.
- **Bodies called unreadable**: none at writing; the operator has not reviewed the stack yet.

## Next

- The operator answers the open point, reviews and merges the stack. A release waits for "A copy before a
  migration that rewrites rows".
- Then lot 2 of the umbrella, the `p2pwatch` hexagon: the self-reconnecting session, the logging port, the
  webui's read side behind use cases, the ports as ABCs split into roles. It removes the twelve `p2pwatch`
  deprecated edges and `logging` from `application/`'s list; lot 3 removes the other nineteen and renames the
  called functions.
