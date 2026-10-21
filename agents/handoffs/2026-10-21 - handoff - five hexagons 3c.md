# Handoff: the five other hexagons, lot 3c of the hexagonal architecture umbrella

Drafted by block 90 from the lot's block reports (#360, #361, #363 to #382) and its own, for the closing block 100
to correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-20-five-hexagons.md` (approved 2026-10-20), its 3c table re-measured on
`main` at `08748882` after 3b merged (`.reviews/lot3c-estimate.md`, gitignored) and re-cut to 22 rows, which the
operator allowed up to 30 blocks. It carries out the three checking tools' part of lot 3 of the umbrella spec
`agents/specs/2026-10-18-hexagonal-architecture.md`, and with it the umbrella's lot 3 ends.

One stack cut from `main` at `08748882` (gh stack #362). Twenty-four blocks: the spec's rows 10 to 90, rows 52 and
60 each split in Act (52 and 53, 60 and 61), then the closing block 100.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #360 | `refactor/vex-reader` |
| 12 | #361 | `refactor/vex-sbom-and-sarif-writers` |
| 14 | #363 | `refactor/vex-premises-in-domain` |
| 20 | #364 | `feat/check-image-claims` |
| 22 | #365 | `refactor/image-claims-cut-over` |
| 24 | #366 | `refactor/vulnerability-scanner` |
| 26 | #367 | `feat/check-stale-claims` |
| 30 | #368 | `feat/vex-source-rules` |
| 32 | #369 | `refactor/source-scanner-gone` |
| 40 | #370 | `feat/check-claim-coverage` |
| 42 | #371 | `refactor/claim-coverage-cut-over` |
| 50 | #372 | `refactor/own-tests-in-domain` |
| 52 | #373 | `refactor/shortfall-in-domain` |
| 53 | #374 | `refactor/test-coverage-reader` |
| 54 | #375 | `feat/check-unit-coverage` |
| 56 | #376 | `refactor/unit-coverage-cut-over` |
| 60 | #377 | `refactor/template-reader` |
| 61 | #378 | `refactor/template-attributes-rename` |
| 62 | #379 | `feat/list-template-attributes` |
| 70 | #380 | `refactor/webui-templates-logic-free` |
| 80 | #381 | `refactor/logic-free-on-jinja-tree` |
| 82 | #382 | `feat/check-logic-free` |
| 90 | (block 90's) | `chore/no-module-patching-rule` |
| 100 | | `docs/five-hexagons-3c-wrap` |

Nothing of the stack is merged. The lot changes the crawler image's webui (block 70); 3b's aMule image changes
are not released either. A release waits for the backlog's "A copy before a migration that rewrites rows" (spec,
"Backlog").

## What was built

- **`vex_checks`, a hexagon** (blocks 10 to 42): three use cases behind driving ports, each returning a report
  with its `problems` (C4, D5): `CheckImageClaims` (`ImageClaimsChecker`, `ImageClaimsReport`),
  `CheckStaleClaims` (`StaleClaimsChecker`, `StaleClaimsReport`), `CheckClaimCoverage` (`ClaimCoverageChecker`,
  `ClaimCoverageReport` of `ClaimCoverageProblem`s). Driven ports: `VexReader` (`JsonVexReader`, one file per
  call), `SbomReader` (`SyftSbomReader`), `SarifWriter` (`JsonSarifWriter`, called by the use case when asked for
  SARIF), `VulnerabilityScanner` (`GrypeVulnerabilityScanner`, replacing the last `Protocol`, `GrypeRunner`) and
  `SourceRuleReader` (`FilesystemSourceRuleReader`, the rules' file names). The domain holds `merge_claims`,
  `evaluate_image_premises` (`packaging.version` on the domain's list), the SBOM's components and the two
  justifications. The application's `vex_location` names a VEX relative to the root `__main__` passes;
  `repo.py`, `vex_io.py`, `sbom.py`, `sarif.py`, `grype.py` and the four old entry functions are gone.
- **The source premises, ast-grep rules** (blocks 30, 32, 42): `packages/vex_checks/ast-grep/`, one rule per
  advisory id (`CVE-2025-15366` for `imaplib`, `CVE-2025-15367` for `poplib`), on the root's `imported-module`
  and a new `dynamically-imported-module` util; scanned by `poe vex-source-claims`, tested in `poe test`. The
  `source-claims` subcommand, `source_scan`, the source family of the descriptors and the registry's source
  premises are gone; `claim-coverage` reads the rules' ids instead.
- **`coverage_checks`, a hexagon** (blocks 50 to 56): `CheckUnitCoverage` behind `UnitCoverageChecker`, returning
  a `UnitCoverageReport` or `NoPerTestCoverage`. `PackageTreeReader` (`FilesystemPackageTreeReader`: the modules,
  the test files, `[tool.coverage_checks]`, a module's source) and `TestCoverageReader` (`CoveragePyReader`, given
  the data file, the package's directory and a report directory). The matching of tests to modules (on
  `PurePath`, `pathlib` on the domain's list) and the shortfall (over `TestCoverage`, `__test__ = False`) moved
  to the domain. `unit_coverage.py` is gone; `main(argv, cwd)`.
- **`template_checks`, a hexagon** (blocks 60 to 82): `ListTemplateAttributes` (`TemplateAttributeLister`,
  `TemplateAttributeListing`) and `CheckLogicFree` (`LogicFreeChecker`, `LogicFreeReport`) over
  `TemplateReader` (`FilesystemTemplateReader`, each template's path and text). The domain parses strings with
  Jinja (`jinja2` allowed in `template_checks`' domain only, by `domain-jinja2.yml`); the logic-free check walks
  the syntax tree and allows D3's nodes only, reporting `<file>:<line>: <Node> is not logic-free`. `read-names`
  is `template-attributes`, the poe task `_template-attributes`; `read_names.py` and `check_templates.py` are
  gone; `main(argv, cwd)`.
- **The webui's templates logic-free** (block 70): the 20 constructs moved into the displays: a `PageNavDisplay`
  carries its previous and next links as 0 or 1 URL, and a node's unknown values are blank in `NodeStateDisplay`.
- **The no-module-patching rule** (block 90): `ast-grep-rules/no-module-patching.yml` refuses the `monkeypatch`
  fixture, `pytest.MonkeyPatch` (`_pytest.monkeypatch` included) and `unittest.mock`'s `patch` (imported, aliased,
  or as `mock.patch`, `unittest.mock.patch` and their `.object`), in every Python file.
- **`AGENTS.md`**: `claim`, `premise`, `source rule` and `test coverage` in the glossary; Naming's `<Thing>Report`
  and `no-protocol-base` over every package's `src`; "No I/O in the core" names `packaging.version`, `pathlib`'s
  `PurePath` and `jinja2`; the Commands section names `_template-attributes` and the source rules' tests; C1 names
  the rule, and C1 and C2 lose their lot 3c clause. `docs/contributing/architecture.md` section 4 describes the six
  hexagons and their rings; `SECURITY.md` the three subcommands and the source rules.

## What an operator sees change

- **A node's page** shows the node id and its creation time blank before the node records its id, where it showed
  `None` (block 70). Every other page renders byte for byte as on `main` (Acceptance 13).
- **Contributors and CI** (no workflow line changed):
  - `python -m vex_checks source-claims` is gone (exit 2, `invalid choice`); `poe vex-source-claims` runs the
    rules (block 32).
  - `claim-coverage`'s messages: `claim has no premise or source rule`, `source rule has no claim`, `has both an
    image premise and a source rule` (new), and `justification '<x>' is not '<expected>'` for `does not match
    premise family` (block 40).
  - `image-claims` and `stale-claims` locate a VEX outside the repository given by a relative path at its absolute
    path, where they echoed it; the workflows pass an in-repository or absolute path, unchanged (block 20).
  - `stale-claims` finds `grype` on the passed environment's `PATH` and runs it in that environment (block 24).
  - `unit-coverage` no longer follows `COVERAGE_FILE` or `COVERAGE_RCFILE`, which nothing sets (block 53).
  - `logic-free` refuses the 8 constructs the regex passed, prints each problem's line and its node's name, and
    reports a template that does not parse as a problem (blocks 80, 82).

The spec's header lists 3a's and 3b's changes only: the closing block may add 3c's with a `(Corrected: ...)`.

## Acceptance

3c meets 2, 5, 7, 13, 9 and 10, and 1, 3 and 4 in full. Re-run by block 90 on 2026-10-21 at its commit unless
noted.

1. `git grep -nE "monkeypatch|MonkeyPatch|mock\.patch|from unittest\.mock import.*patch" -- '*.py'` prints nothing
   (exit 1; 133 lines on the umbrella's `main`, 29 at 3b's top). The rule seen failing through `poe
   code-pattern-check` (exit 1) on an injected `def test_x(monkeypatch):` at
   `packages/vex_checks/tests/test_main.py:64:12` and an injected `with unittest.mock.patch("os.getcwd"):` at
   `packages/amule/tests/domain/test_conf.py:138:6`, both `error[no-module-patching]`; restored, `git status`
   clean. Its tests seen failing first, with the rule's `monkeypatch` arm alone: `FAIL no-module-patching
   .........MMMMM`, the five `unittest.mock` cases `[Missing]`.
2. `grep -rnE "^class \w+\(.*\bProtocol\b" packages/*/src` prints nothing (exit 1). Block 24: `class X(Protocol)`
   injected in the five tooling packages' `src`, `Error: 5 error(s) found in code.`
3. `grep -c "deprecated = true" tach.toml` prints 0 (19 on the umbrella's `main`, 14 at 3b's top); a `tomllib`
   walk of 43 adapter modules and their 96 edges finds no adapter depending on another.
4. `grep -rn "^def main" packages/*/src` lists the six root `__main__.py`s only (10 more on the umbrella's `main`).
5. Blocks 80 and 82, on a copy of the webui's templates with one line appended: the 8 constructs (`~`, an inline
   `if`, `[0]`, `and`, `is`, `with`, `call`, a loop filter) exit 1 with their node's name, where the regex check
   exited 0; `if`, `set`, `macro`, `+`, a filter and a call exit 1 as before; a `for ... else` and a chained
   attribute exit 0, and so do the shipped templates. Block 82 ran each through the command line and the use case
   alike.
7. Partly. `vex-source-claims` (block 30): an injected `import imaplib` fails it in the `src` of `crawler`,
   `matching` and `amule`, `importlib.import_module("poplib")` in the crawler's, and the old scanner gave the same
   exit codes on the same tree; one in `amule_bump` passes both. `stale-claims` (block 26), with a stand-in grype:
   the same lines, exit codes and a byte-identical SARIF as its parent's code. `image-claims` (blocks 12 to 24) on
   the shipped `security/amule.vex.openvex.json` and SBOMs declaring aMule 2.1.1 or 2.3.3: the two `::error::
   CVE-2006-269x` lines and exit 1, or exit 0. `claim-coverage` (blocks 40, 42) on the tree: exit 0, and exit 1 on
   each injected fault. Not run: both image checks on `ghcr.io/mission-titar/mulewatch:latest`'s attested SBOM
   and VEX, on `main` and at the top (Not validated).
9. `git diff --stat 08748882 HEAD` over `deploy`, `security`, the crawler's `migrations`, `packages/amule/docker`,
   `packages/amule/Dockerfile` and `.github/workflows` prints nothing; nothing under `packages/amule` changed.
10. The gate green at every block (each report); CI green on every block's head up to 81, block 82's run in
    progress at writing.
13. Block 70: lot 2's render script, 26 GETs and 11 console POSTs on one seeded catalog, gives 327,802 bytes,
    sha256 `67c4edbcdec2c1af...` (lot 2's value), on `origin/main` and at block 70; `diff` silent, and `← Prev` for
    `← Previous` in `sources.html` shows as one changed line.

## Holistic review

For the closing block.

## Departures from the spec

- **Splits**: block 52 (585 lines, 13 files) into 52 and 53, the shortfall then the reader; block 60 (155 lines,
  20 files) into 60 and 61, the reader then the rename. Both rows are recorded in the spec. No size exemption.
- Block 12: the components in `domain/sbom_components.py`; `write_violations(sarif_path, rule_id, violations,
  vex_relpath)` keeps `build_sarif`'s parameters.
- Block 14: `packaging.version` allowed in every domain, not narrowed to `vex_checks`, since it reads no file.
- Block 20: the VEX's relative path computed in the application (the domain had no `pathlib` then), which block
  26 moved to the shared `vex_location`; `__main__` took the root from `repo.repo_root()` until block 42.
  `AGENTS.md` followed D5 rather than C4's text, which block 22 corrected in the spec at the lead's request.
- Block 24: grype is the bare name `grype`, found on the passed `env`'s `PATH`, not a path as the spec said: the
  workflow installs it on `PATH`, and a lookup in `__main__` would fail every other subcommand without grype.
- Block 30: the dynamic-import matcher is a util of the root's `ast-grep-utils/`. The rules differ from the old
  scanner on forms no shipped code uses: a relative `from .imaplib import x` (no longer flagged), an f-string
  with no interpolation (now flagged), an implicit concatenation `"imap" "lib"` (no longer flagged).
- Block 32: `is_source_premise` and `ProgramNeverInvoked` deleted with the scanner, ahead of row 42: nothing in
  `src` read them, and `dead-code-check` refused them.
- Block 40: `CheckClaimCoverage` receives the VEX paths, not the root; its problems are `ClaimCoverageProblem`s;
  the bijection stays in the use case; the messages changed (above).
- Block 42: the two justifications are constants of `domain/claims.py`; the descriptors describe the image
  premises only, and `test_descriptors.py` went.
- Block 50: `pathlib` on the domain's list for `PurePath`; the sort moved into the domain; `PackageTree` keeps the
  pyproject's word `tests_without_unit`.
- Block 52: `find_shortfall` takes the module's source as a string.
- Block 53: `CoveragePyReader` is also given the package's directory and a report directory;
  `PackageTreeReader.read_module_source`, which the spec's table does not name.
- Block 54: `UnitCoverageChecker` returns `UnitCoverageReport | NoPerTestCoverage`; the problems are strings.
- Blocks 56 and 62: `main(argv, cwd)`, not `main(argv, env, cwd)`: neither package reads an environment
  variable, and `dead-code-check` refuses an unused parameter. The report directory is a `TemporaryDirectory`
  made in `__main__.main`.
- Block 60: only the rings it uses created; the reader returns each template's path with its text.
- Block 61: `print_read_names` and `read_names.py` not renamed, since block 62 deleted both.
- Block 62: the listing a `frozenset`, sorted by the command line; `logic-free`'s directory under `cwd` too.
- Block 80: a `for` over a tuple target is refused (`Tuple` is not in D3's list); an `include` of a non-constant
  name passes; a template that does not parse is a problem, not a crash.
- Block 82: `FakeTemplateReader` in `tests/fakes.py`, taking templates by path.
- Block 90: the rule has no `files`, so it scans every Python file as D1 says; `architecture.md` section 4's
  heading changed (no link pointed at its anchor; `poe docs-build` strict, `No issues found`).

## Names settled by teammates

By rule or precedent, each in its block's report: `merge_claims`, `sbom_components.py`, `write_violations`,
`dpkg_package` and `dpkg_packages_by_name` (block 14's class 1 renames), `vex_location`, `ClaimCoverageProblem`,
`IMAGE_PREMISE_JUSTIFICATION`, `SOURCE_RULE_JUSTIFICATION`, `dynamically-imported-module`, `package_tree.py`,
`find_shortfall`, `read_module_source`, `NoPerTestCoverage`, `find_template_attributes`, `find_logic_constructs`,
`logic_constructs.py`, `TemplateAttributeListing.template_attributes`; the fakes `FakeVexReader`,
`FakeImageClaimsChecker`, `FakeStaleClaimsChecker`, `FakeClaimCoverageChecker`, `FakeVulnerabilityScanner`,
`FakeTemplateReader`, `FakeTemplateAttributeLister`. Block 90: `no-module-patching`, after C1's heading.

## Pitfalls

- **`ast-grep test` passes a test file whose rule is missing**: it prints `Configuration not found! <id>` and
  exits 0 (blocks 30, 60, 90). The red step is a partial rule. The backlog's "ast-grep rule tests bound to their
  rules by design" names this.
- **ast-grep's `has: { field: name }` reaches only the first child under that field** (block 90): `from x import
  a, patch` escaped it. Match the child without the field where the other fields cannot match.
- **ast-grep resolves a rule's `files` against the scan's working directory**, and `ruleDirs`, `utilDirs` and
  `testDir` against the `sgconfig.yml` (block 30): `vex-source-claims` scans from the root with `--config`.
- **coverage.py 7.16 excludes `if TYPE_CHECKING:` by default** (block 53): a config test built on it passes without
  the package's config.
- **vulture reports a `TypedDict`'s keys read only by subscript** as unused (block 53): a private dataclass instead.
- **A same-size mutation undone within the second leaves a stale `.pyc`** that Python still loads (block 54):
  clear `__pycache__` after a mutation check.
- **`poe` refuses to run a `_`-prefixed task** (block 60): run `python -m template_checks <subcommand> <dir>`.
- **In `tach.toml` every module starts with its own `[[modules]]` line** (block 62): a scripted replacement
  spanning two modules must carry it.
- **The logic-free walker compares a node's exact type** (block 80): a node class a later Jinja adds under an
  allowed one is refused until named; none has a subclass in Jinja 3.1.6.
- **An old entry function's test that the cut-over deletes is cheaper adapted than rewritten** (block 20).
- **In zsh, `set -- $pair` does not word-split** (block 30), as 3b met with `$vars`.
- **Host port 4711 is the deployed node's**: never publish it, never touch the `mulewatch-*` containers.

## Not validated

- Acceptance 7 on the real image: `image-claims` and `stale-claims` on `ghcr.io/mission-titar/mulewatch:latest`'s
  attested SBOM and VEX, on `main` and at the top. `stale-claims` never ran against a real grype locally (not
  installed); the release step and the daily `grype-scan` workflow run both image checks.
- The webui's pages driven by hand on a running node (block 70); the render diff covers them.
- CI on blocks 82 and 90 at writing.

## Wrap counts

From `gh run list --branch <branch>` over blocks 10 to 82 on 2026-10-21, before block 90's own run.

- **Runs**: 23 for 22 blocks. Each block's head has one run, green but block 82's, in progress. The other: #365's
  `de3c0122`, cancelled when the block pushed its spec correction (`008de192`, C4) on top. #366's run
  39651903380 had its slow arm64 job cancelled by the lead and rerun green (attempt 2, the same run).
- **Fix-backs**: 0. **Cascaded rebases**: 0. **Runs they re-triggered**: 0.
- **Splits**: 2 in Act (52 at the line bound, 60 at the file bound), after the re-cut from 13 rows to 22 before
  Act. **Exemptions**: none.
- **Bodies called unreadable**: none at writing; the operator has not reviewed the stack yet.

## Next

- The operator reviews and merges the stack, after the lead rebases it onto `main` if `main` moved.
- The closing block deletes the backlog's "Hexagonal architecture" entry and "The logic-free template guard on
  Jinja's syntax tree" (spec, "Backlog").
- "A copy before a migration that rewrites rows" ships before any release; 3b and 3c change both images.
- Then "Contract tests for the fakes", which waited for every port's final shape.
