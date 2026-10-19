# Handoff: hexagonal rings, lot 1b of the hexagonal architecture umbrella

Drafted by block 85 from the lot's block reports (#266, #267, #269 to #278, and block 85's own), for the closing
block 90 to correct: the holistic review's findings and their exits, `BACKLOG.md`, the Wrap counts.

## State

Tier Spec lot. Spec `agents/specs/2026-10-18-hexagonal-foundations.md`, section "Lot 1b", approved by the operator
on 2026-10-18 with lot 1a, and re-measured on 2026-10-19 by a dry run of the whole lot on `013252c`
(`.reviews/lot1b-measure.md`, gitignored: 13 contradictions, each a `(Corrected 2026-10-19: ...)` in the spec,
committed by block 10). The lot carries out the second half of lot 1 of the umbrella spec
`agents/specs/2026-10-18-hexagonal-architecture.md`.

Fourteen blocks, one stack cut from `main` at `013252c` (lot 1a merged):

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
| 85 | (block 90 fills it) | `feat/architecture-gate-all-hexagons` |
| 90 | closing | `docs/hexagonal-rings-wrap` |

Nothing of the stack is merged. The lot changes what both images run (the aMule container's entrypoint and s6
script, logger names in both), so Wrap (f) proposes a release, but not before the backlog's "A copy before a
migration that rewrites rows" ships (spec, section "Backlog").

## What was built

- **`catalog_matching` in its domain ring** (block 10): its ten modules under `catalog_matching/domain/`, their
  tests under `tests/domain/`. The golden corpus test and its fixtures stay at the tests root.
- **The crawler's ports and adapters by side** (block 20): `ports/*.py` to `ports/driven/`, `crawler_control.py`
  to `ports/driving/`; every adapter but lot 1a's driving ones to `adapters/driven/`.
- **The webui's fixtures in `p2pwatch_testing`** (block 25):
  `p2pwatch_testing.adapters.persistence_sqlite.migrated_databases`, registered once by `pytest_plugins` in the
  crawler's `tests/conftest.py`. The connection closer, renamed `close_test_connections`, is no longer autouse:
  each of the twelve webui test modules asks for it with `pytestmark`. `--setup-plan` counts 326 setups before
  and after.
- **The webui as a driving adapter** (block 30): `adapters/driving/webui/` (Starlette routes, uvicorn thread,
  views, formatting, query-string parsing, templates, static files); the three SQLite readers to
  `adapters/driven/persistence_sqlite/`; `matching_read.py` to `application/`; `coverage.py` and
  `CoverageStatus` to `domain/coverage.py`.
- **`p2pwatch_amule` in its rings** (block 40): `conf` in `domain/`; `boot`, `port_sync` and `settings` in
  `adapters/driving/`, as plain modules; `gluetun` in `adapters/driven/`.
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
    distributions to its package's `pyproject.toml`: that, not `visibility`, keeps the hexagons apart (Pitfalls);
  - four ast-grep rules in `code-pattern-check`: `domain-imports`, `ports-imports` and `application-imports`
    (one list per ring, from the imports each ring holds, `logging` in `application/`'s until lot 2), and
    `core-import-names` (`asyncio`, `uuid` and `io` by name, `pathlib` by `PurePath`, no `from asyncio import`);
    a shared matcher in `ast-grep-utils/imported-module.yml`; each rule tested by `ast-grep test` in
    `ast-grep-tests/`, run before the scan;
  - `AGENTS.md`'s architecture rules (the six hexagons, the rings read from the path, the dependency rules, no
    I/O in the core, every module declared), and the passages the lot made stale.

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
  `python -m coverage_checks unit-coverage` (block 73), `python -m amule_bump bump` (block 77). The old module
  paths now exit 0 doing nothing, since their `__main__` guards went.

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
     `coverage_checks`' domain, and passes in `p2pwatch_testing/application/fakes.py`, which the rules exclude.
8. The gate is green at every block's tip. CI ran once per pull request from #266 to #278, attempt 1, green at
   each head, `build-and-verify` on amd64 and arm64 included: blocks 20 (`39175192684`), 50 (`39176957049`) and
   70 (`39178676426`) among them.
9. Blocks 30 and 85: the `git diff -M100%` command prints nothing.

## Departures from the spec

- **Sizes past the spec's row**, all under both bounds but the exempted moves: 50 (156 lines, 13 files; row 116,
  16), 55 (127, 19; row 42, 14, grown by the rename), 70 (498, 16; row 200), 73 (367, 19; row 264, 14), 77
  (238, 10; row 133, 7): the command lines own every option, with their tests. Block 85: 405 lines, 14 files
  (row 430, 13).
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
  distributions, so `visibility` would only check the configuration. Hexagon isolation now rests on each
  package's declared dependencies; only `p2pwatch` declares another workspace package, `catalog-matching`, its
  own domain.
- **ast-grep's lists are one per ring** (block 85): `configparser`, `io`, `ast`, `difflib`, `textwrap` and
  `rapidfuzz` sit in their ring's list for every hexagon, since a rule's files cannot be scoped per hexagon
  without copying its list; `io` is reachable by `StringIO` only. `from asyncio import`, `from uuid import` and
  `from io import` are refused, so every name reached is an attribute the rule sees.

## Spec corrections

- Block 10: the dry run's corrections, each `(Corrected 2026-10-19: ...)` in lot 1b's section.
- Block 85: "The check" and the appendix's ast-grep lists, in the foundations spec; D6 and D15 in the umbrella
  (`check-external` for `visibility`).

## Tests pruned or moved

- Block 30: `tests/domain/test_coverage.py` follows `coverage.py`.
- Block 70: the monkeypatch test of the stale check's default runner is deleted; the checks' `argv` call sites
  are rewritten or deleted.
- Block 73: the tests of the two hand-written usage lines are deleted, argparse's required positional tested in
  the command lines' tests instead.
- Block 77: the default reader's test becomes `tests/test_main.py`'s wiring test; the default Dockerfile test
  becomes the command line's defaults test.

## Class 1 fixes

- Block 10: the em dashes of `format.py`'s docstring.
- Block 20: `docs/contributing/architecture.md`'s code map named the deleted `ports/mule_client.py`.
- Block 25: the moved module's French banner; the closer's docstring.
- Block 30: the em dash of `ed2k_link.py`'s docstring.
- Block 40: `amule_bump`'s checklist named `p2pwatch_amule.boot`; it names `p2pwatch_amule.domain.conf`, where
  the defaults live.
- Block 55: `AGENTS.md`'s `FakeRepo` example.
- Block 85: `docs/contributing/testing.md`'s `lint` job, which named neither tach nor the allowlists.
- Blocks 50, 60, 70, 73, 77, 80: none.

## Class 2 questions

- Block 55: `Repo` breaks the port naming rule. Operator's answer: "Renommer".
- Every other block: none.

## Pitfalls

- **`tach check` never sees an import across distributions**, each `src` with its `pyproject.toml` being a
  package of its own: `p2pwatch_amule` importing `p2pwatch` passes it, and so does every crawler import of
  `catalog_matching`. `visibility` then only refuses a declared edge, which `exact` already fails as unused.
  Block 80's "a cross-hexagon import is already an undeclared edge" did not hold. `tach check-external` and
  deptry both refuse the import.
- **The deprecated edges print 90 `[WARN]` lines** in every gate run, by design.
- **ast-grep's `field` on a relational rule matches the first child of that field only**: `inside: { kind:
  import_statement, field: name }` misses `sqlite3` in `import dataclasses, sqlite3`. The shared matcher tests
  the direct parent instead, and a rule test holds that case.
- **`ast-grep test --skip-snapshot-tests` still checks each case's verdict** (a `[Missing]` fails it); it only
  skips the snapshots of the messages, which would be generated files.
- **The ast-grep rules exclude `packages/crawler_testing/`**, whose `application/` holds fakes.
- **The old module paths of the checks exit 0 doing nothing** (blocks 50, 70, 73).
- **A same-size `sed` swap undone within a second leaves stale bytecode** (`.pyc` keyed on mtime in seconds and
  size): clear `__pycache__` (block 50).
- **git pairs moved empty `__init__.py` files arbitrarily** (block 20); harmless.
- **Port-sync's logger is a string**, since `__name__` is `__main__` under `-m` (block 40).
- **`SubprocessGrypeRunner.run` keeps its `# pragma: no cover`**: `test_main.py` runs it, its own tests do not
  (block 70). That `test_main.py` needs `/bin/sh` for its fake `grype`.
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

To be written by block 90.

## Wrap counts

From `gh run list --branch <branch>` and `git rev-parse origin/<branch>` on 2026-10-19, before block 85 was
pushed.

- **Runs**: one per pull request from #266 to #278, twelve, each at its branch's current head, attempt 1, green.
  #267 also had one run cancelled by a second push (`5e75ec0`, then `f1ffbfe`).
- **Fix-backs**: none reached a pushed branch but #267's second push.
- **Cascaded rebases**: none: no other pushed head moved.
- **Splits**: none beyond the re-measured table. **Exemptions**: five, blocks 10, 20, 30, 40, 60.
- **Bodies called unreadable**: none at writing.

## Next

- The holistic review over the stack, then the closing block 90.
- The operator reviews and merges the stack. A release waits for "A copy before a migration that rewrites rows".
- Then lot 2 of the umbrella, the `p2pwatch` hexagon, which removes the twelve `p2pwatch` deprecated edges and
  `logging` from `application/`'s list; lot 3 removes the other nineteen.
