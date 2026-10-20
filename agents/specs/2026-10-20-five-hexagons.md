# Hexagonal architecture, lot 3: the five other hexagons

- Date: 2026-10-20. Status: approved by the operator on 2026-10-20, after Discuss and a review
  (`.reviews/lot3-spec.md`: 0 critical, 12 major, 19 minor, all answered here).
- Tier: Spec, two lots that merge one after the other, each with its stack and holistic review: 3a, the crawler's
  leftovers, `amule_bump` and `p2pwatch_amule`; 3b, the three checking tools, the rule and the documentation. Why:
  measured at 21 to 25 blocks, over the cap of 19 (`.reviews/lot3-estimate.md`); the operator chose the cut.
- Origin: lot 3 of the umbrella spec `agents/specs/2026-10-18-hexagonal-architecture.md` (D18), whose decisions this
  one applies without restating them. It absorbs the backlog entry "The logic-free template guard on Jinja's syntax
  tree" (section 7 of `agents/specs/2026-10-15-gate-tooling.md`).
- What an operator sees change: nothing. The aMule image boots and syncs its port as before; its environment
  variables, its s6 services and their names do not change, and port-sync keeps the two logger names
  `docs/migration-4x.md` documents (`p2pwatch_amule.adapters.driving.port_sync`, `p2pwatch_amule.adapters.driven.gluetun`),
  handed to `StdlibLogger` as lot 2 did for the crawler.
- Paths are under `packages/<pkg>/src/<module>/` unless noted. The measurements are in the appendix.

## Summary

- **Every hexagon gets its core**: `p2pwatch_amule`, `vex_checks`, `template_checks`, `coverage_checks` and
  `amule_bump` each gain use cases behind driving ports and do their I/O through driven ports that adapters
  implement. Their command lines call the driving ports; every entry function still named `main` goes.
- **No test uses `monkeypatch`**, in any package, integration tests included, and an ast-grep rule refuses it.
- **A third-party tool where one covers ours**: the source premises of the VEX become ast-grep rules. The other
  tools stay ours, each for a measured reason.
- **The logic-free template check reads Jinja's syntax tree**, and the logic it missed moves into the views.

## Conventions this lot sets

Settled with the operator in Discuss and Spec: the rules a good programmer would not guess, or that amend one
`AGENTS.md` already states. Each goes into `AGENTS.md` in the block that first applies it, so a rule never describes
a tree that does not follow it yet (umbrella D19); the block is named beside each. The lot's other choices (D4's
parameter names, `__test__ = False`, a rule's id as its file name, `ResourceWarning` as an error) stay decisions of
this spec: they apply a rule `AGENTS.md` already has, or a tool enforces them itself.

- **C1. No module patching in a test**: no `monkeypatch`, `pytest.MonkeyPatch` or `unittest.mock.patch`. Process
  state is read only by a `__main__.py` and passed down as values; a constant a test tunes is a parameter; a
  function a test replaces is passed to what calls it, a port when the core needs it, a typed `Callable` inside an
  adapter. The composition passes the real value, never a parameter's default (Corrected: defaults were not
  excluded). What is part of an adapter's code (its SQL, its migration scripts, the SQL functions they call) is
  no parameter: a test that tunes it tests a generic mechanism, which moves apart and receives it (Corrected:
  the migration runner and the SQL functions' memo, block 10). Hard rules, 3b 90 (the rule that enforces it); the three
  replacements in Hard rules from 3a 10.
- **C2. An adapter receives from the composition what it drives**: a directory or a file, a URL or an address, a
  command runner or an executable's path. Its unit test hands it a local stand-in, the integration suites the real
  one. Hard rules, 3a 12.
- **C3. An adapter is named by the system it adapts**, not by the Python module it uses: `FilesystemTemplateReader`,
  `CoveragePyReader`, `S6ServiceSupervisor`, `GluetunForwardedPortReader`. A module is the name only when it is
  the system (`ShutilFreeSpaceMeter`, `StdlibLogger`). `PathlibCatalogFinder` becomes `FilesystemCatalogFinder`.
  Naming, 3a 12.
- **C4. A check returns a report**: a `<Thing>Report` response model with a `problems` field, which the command
  line prints or writes. Naming, 3b 20.
- **C5. A value taken when the operator sets nothing is the domain's**: a key absent from `crawler.yml`, an
  environment variable left unset. The parser applies the domain's value; a value a component receives comes
  from the composition (C1, C2). Hard rules, 3a 16 (Corrected: added after the operator's approval, so that no
  value is written in an adapter).

## Decisions

- **D1. No module patching in any test.** A rule in `ast-grep-rules/` refuses the `monkeypatch` fixture,
  `pytest.MonkeyPatch` and `unittest.mock`'s `patch` in every Python file. Why: with ports and fakes, a test never
  needs to patch a module; a test that does tests the module's insides, and nothing enforces the convention today
  (12 crawler and test support files still use it). The three replacements:
  - **Process state** (`os.environ`, the working directory, the root logger) is read only by a `__main__.py` and
    passed down as values: `main(argv, env, cwd)`, with no `argv=None` falling back to `sys.argv` (Corrected: the
    six command lines' `run(argv=None)`, each fixed by the block that touches it), the root logger handed to what configures it (the command line,
    and the crawler's composition, which sets its level). Why: it is the composition's to read, as `CrawlerApp`
    already receives `env=os.environ`.
  - **A module constant a test tunes** (`_PROGRESS_EVERY`, the aMule paths, `PREMISES`) becomes a
    parameter, the composition passing the real value, never a default of the parameter (Corrected: defaults were
    not excluded). Why: the test then says what it sets, and one rule leaves nothing to decide case by case.
  - **A function a test replaces** is passed to what calls it: a driven port when the core needs it, a plain typed
    `Callable` parameter when an adapter uses it internally (`start_http_server`, a parameter of
    `start_metrics_server`, which the composition passes). Why: an ABC of one method that no core consumes would
    be a port in name only.
  - **What a test tuned inside an adapter's own code** moves into a generic piece that receives it: the migration
    runner takes its scripts, so `open_catalog(path)` and `open_local(path)` keep applying their own; a memo
    takes the function it memoizes, so `register_sql_functions` keeps `content_hash` and `fold_raw_meta`, its
    tests checking their output. Why: the scripts and the hash are the database's definition, and passing others
    would break the stored rows. Accepted limit: no test proves `register_sql_functions` registers them memoized;
    the line shows it (Corrected: `_MIGRATIONS`, `content_hash` and `fold_raw_meta` were parameters).

  **An adapter receives from the composition what it drives**: a directory or a file, a URL or an address, a
  command runner or an executable's path. Its unit test hands it a local stand-in (`tmp_path`, a loopback server, a
  runner that records the commands it is given); the integration suites hand it the real one, as the compose smoke
  runs the boot step as root under s6. Why: the unit test checks what the adapter asks of the system, the
  integration test that the system answers as we believe (umbrella D12); `groupadd`, `useradd`, a `chown` to
  `PUID:PGID`, amuleapi's `extra_groups=[]` and `s6-svc` cannot run in the gate, which is not root and runs no s6,
  so a rule that wanted the real system in a unit test would need an exception per adapter. About 30 driven
  adapters already follow it (`.reviews/lot3-adapter-sweep.md` holds the sweep's list); this lot brings the rest:
  the aMule adapters, `GrypeVulnerabilityScanner` (the executable's path), `GitHubRepoReader` (the API URL), and the
  command lines' default paths, resolved against the `cwd` and the temporary directory `__main__` passes.
- **D1b. No unclosed connection.** The crawler's pytest config turns `ResourceWarning` into an error, and
  `close_test_connections` goes: the readers' tests open `with ReaderProvider(...)`, and seeding goes through
  `contextlib.closing(sqlite3.connect(...))`. Why: the fixture patches `sqlite3.connect` to close what tests leak,
  and nothing fails if a test leaks; an error makes the leak visible where it happens.
- **D2. Third-party tools, verified before deciding** (`.reviews/lot3-tools-*.md`, `.reviews/lot3-trial-*.md`):
  - **`source-claims` becomes ast-grep rules**, one per source premise, in `packages/vex_checks/ast-grep/` with
    their tests and their own `sgconfig.yml` (its `utilDirs` reaching the root's `ast-grep-utils/`), the scan run
    by the poe task `vex-source-claims` where it runs today, the rules' tests by `poe test`. Both source premises
    are `ModuleNotImported` (`imaplib`, `poplib`). Each rule matches what the scanner matches: an `import` or
    `from ... import` of the module (the existing `imported-module` matcher), and `importlib.import_module`,
    `import_module` and `__import__` with the module's name as a constant; and its `files` are the scanner's, the
    `src` of `crawler`, `matching` and `amule`. A rule's id is the advisory id it backs, so it implies the
    justification `vulnerable_code_not_in_execute_path`. Why: the AST scanner is ours for no reason a tool lacks;
    the rules stay in the VEX package, apart from `code-pattern-check`, because they check a claim, not a code
    pattern (the operator's choice); their tests join the gate because the scanner's tests are in it today. The
    `source-claims` subcommand, `CheckSourceClaims` and its port go with the scanner, and so does
    `is_source_premise`, which only that check calls.
  - **`claim-coverage`, `image-claims` stay ours**: no tool ties an OpenVEX claim to a fact of the repository or
    judges its justification; Grype, vexctl and Trivy only apply a VEX.
  - **`stale-claims` stays as it is**: `grype --vex -o json`'s `ignoredMatches` answers another question (does a
    claim apply), as the trial showed on both images.
  - **`amule_bump` stays ours**: Renovate or updatecli could rewrite the two `ARG`s (38 lines), but not the pull
    request's body, which is most of the package; Dependabot cannot rewrite an `ARG`.
  - **`coverage_checks` stays ours**: `coverage report --contexts` gives the same verdict on 172 modules, but our
    check is already coverage.py's analysis; it would be 3.7 times slower and would wrongly fail a module first
    imported inside a test.
  - **port-sync stays ours**: gluetun's port-forwarding command runs in gluetun's container, which reaches neither
    s6 nor `amule.conf`.
- **D3. `template_checks` reads Jinja's syntax tree.** `CheckLogicFree` allows these nodes only: `Template`,
  `Output`, `TemplateData`, `Name`, `Getattr` at any depth, `For` with no `test` (an `else` allowed), `Extends`,
  `Block`, `Include`, and `Const` only as the template name of `extends` or `include`. Why: the regex check passes
  all 8 logic constructs it was tested with (`~`, an inline `if`, `[0]`, `and`, `is`, `with`, `call`, a loop
  filter); a chained attribute reads a value without computing one, and a loop's `else` is the empty-state text,
  with no expression (the shipped templates hold 31 and 28). The 20 constructs the tree finds in today's templates
  move into the `<Thing>Display`s (appendix). `jinja2` is allowed in `template_checks`' domain only, by a rule of
  its own like `domain-configparser.yml`, and the domain parses strings (`Environment().parse(text)`), never a
  loader. Why: the parse is pure computation, as `rapidfuzz` is for the crawler, but jinja2 can also read files.
- **D4. Each check has one word** for its module, its subcommand and the command line's parameter: `logic-free`
  (`check_logic_free.py`), `template-attributes` (the subcommand `read-names`, the poe task `_template-read-names`
  and its variable `TEMPLATE_READ_NAMES` renamed with it), `port-sync`. The command line's parameters name the
  driving port they receive, as the crawler's do (`crawler_runner`): `port_sync_loop_runner` replaces
  `sync_listen_port`, `logic_free_checker` replaces `check_logic_free`. Why: one concept, one name in every layer
  (`AGENTS.md`'s Naming); `port-sync` is already the s6 service's and the environment variables' word.
- **D5. A check returns a report** of its problems, a `<Thing>Report` response model with a `problems` field, and
  the command line prints them or writes them as SARIF. Why: the image checks write SARIF instead of failing, so a
  problem is an outcome, not an error; what a check returns is its report (the operator's word).

## The hexagons

The use cases, the ports, the response models and the adapters' names were settled with the operator; the adapters
follow C3.

### `p2pwatch_amule`

| Driving port | Use case | Returns |
|---|---|---|
| `ContainerBooter` | `BootContainer` | nothing, raises on failure |
| `PortSyncLoopRunner` | `RunPortSyncLoop` | nothing, runs until stopped |

| Driven port | Adapter | What it does |
|---|---|---|
| `AmuleConfReader`, `AmuleConfWriter` | `PosixAmuleConf` | read, write `amule.conf` (atomically, `os.replace`) |
| `ServiceSupervisor` | `S6ServiceSupervisor` | stop and start amuled; set or clear port-sync's `down` file |
| `ForwardedPortReader` | `GluetunForwardedPortReader` | read gluetun's forwarded port, or none |
| `AccountManager` | `PosixAccountManager` | find or create the `amule` user and group |
| `MountPointPreparer` | `PosixMountPointPreparer` | create the download mount points, chown them |
| `AdminPasswordSetter` | `AmuleApiAdminPasswordSetter` | run `amuleapi --set-admin-pass` |
| `MonotonicClock` | `SystemMonotonicClock` | `now`, `sleep`, this hexagon's own copy |
| `Logger` | `StdlibLogger` | log under the name it is given: port-sync's two documented names |

- The environment's validation (`settings.py`) and port-sync's decision (compare the ports, the restart window) move
  to the domain. A refused variable raises a domain error naming it; only the command line exits. Why: they are
  logic, and `sys.exit` in a parser hides the error from its caller.
- `packages/amule/` loses its `TID251` exemption, and `banned-api` gains `time.sleep`: only `SystemMonotonicClock`
  reads the clock or sleeps. `AGENTS.md`'s hard rule changes with it (umbrella D19). Why: today `time.sleep` is
  banned nowhere, so the exemption's removal alone would let port-sync keep sleeping outside its clock.

### `vex_checks`

| Driving port | Use case | Returns |
|---|---|---|
| `ImageClaimsChecker` | `CheckImageClaims` | `ImageClaimsReport` |
| `StaleClaimsChecker` | `CheckStaleClaims` | `StaleClaimsReport` |
| `ClaimCoverageChecker` | `CheckClaimCoverage` | `ClaimCoverageReport` |

| Driven port | Adapter | What it does |
|---|---|---|
| `VexReader` | `JsonVexReader` | read the claims of `security/*.vex.openvex.json` |
| `SbomReader` | `SyftSbomReader` | read the packages and declared components of a Syft-JSON SBOM |
| `VulnerabilityScanner` | `GrypeVulnerabilityScanner` | scan an SBOM, return the vulnerabilities found (replaces the `GrypeRunner` `Protocol`) |
| `SarifWriter` | `JsonSarifWriter` | write the SARIF report |
| `SourceRuleReader` | `FilesystemSourceRuleReader` | list the ast-grep source rules' ids, for `claim-coverage` |

- The premise evaluation and the claims' merge move to the domain; the `::error::` lines are printed by the command
  line from the response model; `__main__` computes the repository's root and passes it.
- `claim-coverage`'s bijection runs over the VEX claims on one side and, on the other, the image premises of the
  registry plus the source rules' ids, refusing an id present in both.
- A rule's id is its file's name, as every rule of `ast-grep-rules/` already is, so `FilesystemSourceRuleReader` lists
  file names and parses no YAML. Why: no new dependency (`pyyaml`) for one field.

### `template_checks`

| Driving port | Use case | Returns |
|---|---|---|
| `LogicFreeChecker` | `CheckLogicFree` | `LogicFreeReport` |
| `TemplateAttributeLister` | `ListTemplateAttributes` | `TemplateAttributeListing` |

| Driven port | Adapter | What it does |
|---|---|---|
| `TemplateReader` | `FilesystemTemplateReader` | read the text of every `*.html` under a directory |

### `coverage_checks`

| Driving port | Use case | Returns |
|---|---|---|
| `UnitCoverageChecker` | `CheckUnitCoverage` | `UnitCoverageReport` |

| Driven port | Adapter | What it does |
|---|---|---|
| `TestCoverageReader` | `CoveragePyReader` | read the statements and branches each test ran, from `.coverage` |
| `PackageTreeReader` | `FilesystemPackageTreeReader` | list the package's modules and test files, read `[tool.coverage_checks]` |

- `own_tests.py`'s matching of tests to modules moves to the domain; `__main__` passes the package's directory.
- `TestCoverageReader`, not `CoverageReader`: the crawler's `CoverageReader` reads a target's coverage, another
  concept (the operator's choice). The port sets `__test__ = False`, so pytest never collects a class named `Test...`
  that a test module imports. The glossary gains `test coverage` beside `coverage` (3b 52).

### `amule_bump`

| Driving port | Use case | Returns |
|---|---|---|
| `AmuleBumper` | `BumpAmule` | `AmuleBump`: the new pin and the body, or nothing to do |

| Driven port | Adapter | What it does |
|---|---|---|
| `RepoReader` (exists) | `GitHubRepoReader` | its methods start with `read_` and return domain types, not GitHub's JSON |
| `DockerfileReader`, `DockerfileWriter` | `FilesystemDockerfile` | read, write the Dockerfile |
| `PullRequestBodyWriter` | `FilesystemPullRequestBodyWriter` | write the body file |
| `StepOutputWriter` | `GitHubStepOutputWriter` | append to `GITHUB_OUTPUT` |

- GitHub's API URL becomes a value of the composition root, as the amuleapi endpoint is for the crawler (umbrella
  D13): the wiring test passes a loopback server.

### The crawler's leftovers

The 12 crawler and `p2pwatch_testing` files still on `monkeypatch` (appendix) follow D1, and
`close_test_connections` goes by D1b: still needed today, since the 5 test files that use it build
`ReaderProvider(...)` without `with` and seed through `with sqlite3.connect(...)`, which does not close.

Six parameter defaults only tests change follow C1 (Corrected: added after the operator's approval,
`.reviews/lot3-default-sweep.md`): `AmuleApiClient`'s `transport` and `timeout_seconds`, `AppriseNotifier`'s
`apprise_factory`, `RandomJitterGenerator`'s `jitter_seed`, `UvicornServerThread`'s `start_timeout_seconds` and
`serving_resources`. The defaults `crawler_config.py` takes for an absent key move to the domain (C5); the
doubles of `p2pwatch_testing` keep theirs, which are test data.

## `AGENTS.md` and the documentation

Each changes in the block that makes it false.

- `AGENTS.md`: the conventions C1 to C5, each in the block the section "Conventions this lot sets" names.
- `AGENTS.md`: the `TID251` exemption of `packages/amule/` goes (3a 54, umbrella D19); the hard rules gain "no
  module patching" (3b 90); "No I/O in the core" names `jinja2` in `template_checks`' domain (3b 60); the Commands
  section names `_template-attributes` (3b 60); the subsystem table's rows for port-sync and the container boot
  follow their new paths (3a 44, 54); the glossary gains `claim`, `premise` and `source rule` (3b 12, 30), and
  Naming the `<Thing>Report` response model with its `problems` (3b 20).
- `docs/contributing/architecture.md`: section 4 describes the six hexagons and their rings (3b 90); sections 9 and
  12 follow port-sync's and the boot's new paths (3a 54).
- `docs/contributing/amule-bump.md` follows `application/body.py` (3a 20).
- `SECURITY.md`: `vex_checks` has three subcommands, and the source claims are ast-grep rules (3b 32).
- The strings that stay: the subcommands `boot` and `port-sync` keep their names, so `entrypoint.sh` and
  `services.d/port-sync/run` do not change; `image-claims` and `stale-claims` keep theirs and their options, so the
  workflows' lines do not change.

## Blocks

Estimates by a Sonnet agent on `main` at `38bfe15`, before any code, about 20 % either way
(`.reviews/lot3-estimate.md`); each teammate measures its block and splits it at a bound. No block is purely
mechanical, so none takes the size exemption. Headroom under the cap of 19: 3 splits for 3a (Corrected: 5 before
blocks 14 and 16), 5 for 3b; five rows sit
at 450 to 480 lines (3a 20, 40, 44, 52; 3b 52), and 3a 40's fallback is to hand its fakes to 42.

Every block leaves its new surface called by production code, since `dead-code-check` reports a class only tests
call: the old entry function delegates to what the block adds until a later block deletes it.

### Lot 3a: the crawler's leftovers, `amule_bump`, `p2pwatch_amule`

| # | Branch | Holds | Lines, files (est.) |
|---|---|---|---|
| 10 | `test/crawler-constants-as-parameters` | this spec; `_PROGRESS_EVERY` a parameter; the migration runner and the SQL functions' memo apart (Corrected: were `_MIGRATIONS`, `_configure`, `_load_scripts`, `content_hash`, `fold_raw_meta` as parameters); the migration tests and `older_catalog.py` off `monkeypatch` | 300, 12 |
| 11 | `test/crawler-connections-closed` | D1b: `ResourceWarning` an error; the readers' tests open and seed with closing; `close_test_connections` gone | 350, 8 |
| 12 | `test/crawler-process-state-as-values` | `main(argv, env, cwd)`; the root logger passed; `start_http_server` a parameter of `start_metrics_server`; the command line's default paths against the given `cwd`; `FilesystemCatalogFinder` (C3); the finder, the command line and the compose smoke off `monkeypatch` | 250, 9 |
| 14 | `refactor/adapter-values-from-composition` | the six parameter defaults of the crawler's adapters gone, the composition passing them (Corrected: added) | 110, 13 |
| 16 | `refactor/config-defaults-in-domain` | the defaults of `crawler.yml`'s absent keys into the domain; C5 in `AGENTS.md` (Corrected: added) | 185, 6 |
| 20 | `refactor/bump-amule` | `BumpAmule` behind `AmuleBumper`; the three writers and their adapters; the default paths against the given `cwd` and temporary directory; `wrap`'s width from the composition (Corrected: added); `test_bump` rewritten; `docs/contributing/amule-bump.md` | 450, 16 |
| 22 | `refactor/repo-reader-domain-types` | `RepoReader`'s `read_` methods on domain types; GitHub's API URL as a composition value; the loopback test | 300, 12 |
| 30 | `refactor/amule-settings-in-domain` | the environment's validation into the domain, its error, and the values of unset variables (C5, Corrected: added); `env` and the paths as values from `__main__` | 300, 10 |
| 40 | `feat/boot-container` | `BootContainer` behind `ContainerBooter`; `AmuleConfReader`, `AmuleConfWriter`, `PosixAmuleConf`; `boot.main` delegating to `BootContainer` | 480, 14 |
| 42 | `feat/boot-accounts-and-mount-points` | `AccountManager`, `MountPointPreparer` and their adapters; `BootContainer` gains the two steps, `boot.py` loses them | 300, 10 |
| 44 | `feat/boot-password-and-supervisor` | `AdminPasswordSetter`, `ServiceSupervisor`'s `down` file; `boot.py` and `test_boot.py` gone; `AGENTS.md`'s boot row | 450, 15 |
| 50 | `refactor/port-sync-decision-in-domain` | port-sync's decision into the domain; `GluetunForwardedPortReader` on a loopback server; `SystemMonotonicClock`, `StdlibLogger`; `port_sync.main` reading through them | 400, 14 |
| 52 | `feat/port-sync-loop` | `RunPortSyncLoop` behind `PortSyncLoopRunner`; the supervisor's stop and start; `port_sync.main` delegating to it | 450, 14 |
| 54 | `refactor/port-sync-wired` | the composition and `port_sync_loop_runner` (D4); `port_sync.py` gone; the `TID251` exemption, `time.sleep` banned; `AGENTS.md`'s rule and row; `architecture.md` sections 9 and 12 | 350, 11 |
| 56 | `test/port-sync-smoke` | a compose smoke case: a stand-in for gluetun's `/v1/portforward` (a static file served by `python -m http.server`), port-sync rewrites `Port` and `UDPPort` and restarts amuled | 150, 3 |
| 60 | `docs/five-hexagons-3a-wrap` | closing block: the holistic findings, backlog, handoff | |

### Lot 3b: `vex_checks`, `coverage_checks`, `template_checks`, the rule

| # | Branch | Holds | Lines, files (est.) |
|---|---|---|---|
| 10 | `refactor/vex-reader` | `VexReader`, `JsonVexReader`; the claims' merge into the domain | 250, 8 |
| 12 | `refactor/vex-premises-in-domain` | `SbomReader`, `SyftSbomReader`; the premise evaluation into the domain; `claim`, `premise` in the glossary | 300, 9 |
| 20 | `feat/check-image-claims` | `CheckImageClaims` behind `ImageClaimsChecker`; `SarifWriter`; the command line prints problems or writes SARIF; `<Thing>Report` in Naming | 430, 14 |
| 22 | `feat/check-stale-claims` | `CheckStaleClaims` behind `StaleClaimsChecker`; `VulnerabilityScanner` for the last `Protocol`, given grype's path; `no-protocol-base` over every package's `src`; `__main__` | 330, 13 |
| 30 | `feat/vex-source-rules` | the source premises as ast-grep rules with their tests and `sgconfig.yml`; the poe task on them, their tests in `poe test`; `source rule` in the glossary | 200, 8 |
| 32 | `refactor/source-scanner-gone` | `source_scan`, `is_source_premise`, the `source-claims` subcommand and its check gone; `SECURITY.md` | 300, 11 |
| 40 | `feat/check-claim-coverage` | `CheckClaimCoverage` over the claims, the image premises and `SourceRuleReader` | 400, 14 |
| 50 | `refactor/own-tests-in-domain` | `PackageTreeReader`; the matching of tests to modules into the domain | 400, 12 |
| 52 | `feat/check-unit-coverage` | `CheckUnitCoverage` behind `UnitCoverageChecker`; `TestCoverageReader`; no working directory | 480, 12 |
| 60 | `refactor/template-attributes` | `ListTemplateAttributes` on Jinja's tree in the domain; `TemplateReader`; `jinja2` allowed in that domain; the rename (D4) | 400, 16 |
| 70 | `refactor/webui-templates-logic-free` | the 20 constructs into the `<Thing>Display`s | 130, 9 |
| 80 | `feat/logic-free-on-jinja-tree` | `CheckLogicFree` on the tree; the regex check gone | 380, 14 |
| 90 | `chore/no-module-patching-rule` | the ast-grep rule and its test; `AGENTS.md`'s hard rules; `architecture.md` section 4 | 210, 6 |
| 100 | `docs/five-hexagons-3b-wrap` | closing block: the holistic findings, backlog, handoff | |

- 3a's block 10 carries this spec. 3b starts once 3a has merged, on the tree it leaves, and re-measures its blocks
  first.
- In 3b, block 70 comes before 80 so that 80's check passes on the templates it lands on, and block 90 comes last
  among the code blocks: the rule fails until every package is off `monkeypatch`.
- 3a's block 56 adds what no suite runs today: the compose smoke starts port-sync without gluetun and only checks
  it stays down, so the path that stops amuled, rewrites the ports and starts it again is tested nowhere, and 3a
  rewrites it whole.

## Acceptance

3a meets 6, 8, 11 and 12, 9 and 10, and 1, 3 and 4 for its packages; 3b meets 2, 5, 7, 13, 9 and 10, and 1, 3 and
4 in full.

1. **No module patching**: `git grep -nE "monkeypatch|MonkeyPatch|mock\.patch|from unittest\.mock import.*patch" -- '*.py'`
   prints nothing (on `main`: 133 lines in 27 files), and the ast-grep rule is seen failing on an injected
   `def test_x(monkeypatch)` and an injected `unittest.mock.patch`.
2. **No `Protocol` in any hexagon**: `grep -rnE "^class \w+\(.*\bProtocol\b" packages/*/src` prints nothing (on
   `main`: `GrypeRunner`), and `no-protocol-base` is seen failing on an injected `class X(Protocol)` in each of the
   five tooling packages' `src`.
3. **No deprecated edge left, none rewritten as a plain one**: `grep -c "deprecated = true" tach.toml` prints 0 (on
   `main`: 19), and no module under an `adapters` path lists another `adapters` module in its `depends_on`.
4. **No entry function named `main`** but the root `__main__.py`s': `grep -rn "^def main" packages/*/src` lists only
   `__main__.py` files (on `main`: 10 more).
5. **The logic-free check fails on logic**: `python -m template_checks logic-free <dir>` on a copy of the templates
   fails for each of the 8 constructs injected, and for what the regex check refused (`if`, `set`, `macro`, an
   operator, a filter, a call); it passes on a `for ... else` and a chained attribute, and on the shipped templates.
   On `main` the 8 constructs pass.
6. **The aMule container behaves as before**: CI's compose smoke, and the crawler's `api_integration`,
   `download_integration` and `orchestration_integration` suites against `p2pwatch-amule`, pass on amd64 and arm64 at
   3a's blocks 44 and 56; boot's refusal messages and port-sync's log lines, with their logger names, are the same
   set on `main` and at the top (`git grep -hE "sys.exit|_logger\.(info|warning|error)|logger\.(info|warning|error)"`
   over `packages/amule/src` on both sides, then the messages compared).
7. **The VEX checks give the same verdicts**: `image-claims` and `stale-claims` on
   `ghcr.io/mission-titar/mulewatch:latest`'s attested SBOM and VEX (v4.1.0, verified downloadable on 2026-10-20),
   and `claim-coverage` on the tree, give the same exit codes and the same (advisory, file) problems on `main` and
   at the top of 3b. `vex-source-claims` fails on an injected `import imaplib` in each of `packages/crawler/src`,
   `packages/matching/src` and `packages/amule/src`, and on an `importlib.import_module("poplib")`; it passes on one
   in `packages/amule_bump/src`; on `main` and at the top alike.
8. **`amule_bump` writes the same thing**: a loopback server serves recorded GitHub answers for a release newer than
   the pin; `main`'s side runs from a scratch checkout with the API URL edited to the server, the top's with the URL
   passed; both dry runs, on a copied Dockerfile with an older pin, print the same new pin and the same body.
9. **Nothing out of scope changes**: the diff shows no change under `deploy/`, `security/`, the crawler's
   `migrations/`, `packages/amule/docker/`, `packages/amule/Dockerfile` and `.github/workflows/`, nor to an
   environment variable's name in `packages/amule/`.
10. **The gate is green** at every block.
11. **No unclosed connection**: the crawler's pytest config has `error::ResourceWarning`, and an injected test that
    leaves a `sqlite3.connect` open fails the suite.
12. **Port-sync syncs**: the smoke case of 3a's block 56 sees `amule.conf`'s `Port` and `UDPPort` take the stand-in's
    port and amuled's pid change; with the stand-in serving the current port, neither changes.
13. **The pages render as before**: a throwaway script renders the same seeded GETs as lot 2's Acceptance 9 on
    `main` and at 3b's block 70; `diff` prints nothing, and one deliberate template edit shows in it.

## Backlog

- **Hexagonal architecture**: 3a's Wrap narrows the lot 3 sub-item to 3b; 3b's Wrap deletes it, and with it the
  entry.
- **The logic-free template guard on Jinja's syntax tree**: absorbed (D3), deleted at 3b's Wrap.
- **Contract tests for the fakes** stays open and follows this lot (the operator's order): it needs every port's
  final shape, which this lot gives the five other hexagons.
- **The ast-grep rule tests bound to their rules by design** stays open; this lot adds rules under the current
  layout, which that entry will move.
- **The VEX's Python claims applied by Grype** stays open: it changes `security/*.vex.openvex.json`, which this lot
  leaves alone (Acceptance 9).
- **The Grype scan back on p2pwatch at the v5 release** stays open: a release step.
- **A copy before a migration that rewrites rows** stays open and ships before the next release; this lot changes
  the aMule image, so it is not released before that. It changes the migration runner whose constants 3a's block 10
  turns into parameters: whichever lands second rebases on the other, with no design at stake.
- **The metrics served by the webui on 8080** stays open: it deletes `start_metrics_server`, which 3a's block 12
  gives a parameter; that block's change is small and goes with the function.
- **Test quality**, **Mutation testing in the gate**, **Adopt ty**, **Multi network, stage 5**, **Sort the files
  view by first seen**, **The webui in the visitor's time zone**, **Every stamp an integer of microseconds** and
  **The node page shows a node id set in `crawler.yml`** stay open: none touches what this lot changes.

## Appendix: measurements

Taken on `main` at `38bfe15` on 2026-10-20. Re-run before acting on one.

- `monkeypatch` per package, `grep -rhoE "monkeypatch\.[a-z_]+"` over each package's tests: amule 38 (22 `setattr`,
  12 `setenv`, 4 `delenv`), vex_checks 13 (11 `setattr`, 2 `setenv`), amule_bump 4, coverage_checks 3 `chdir`,
  template_checks 0; crawler, matching and `p2pwatch_testing`, `grep -rln monkeypatch`: 12 files (`test_main.py`,
  `test_argparse_command_line.py`, `test_pathlib_catalog_finder.py`, `test_prometheus_metrics_recorder.py`,
  `test_connection.py`, `test_variants.py`, `test_compose_smoke.py`, `test_reevaluate_catalog.py`,
  `test_migration_0007.py`, `test_migration_0008.py`, `migrated_databases.py`, `older_catalog.py`).
- Source lines: amule 412, vex_checks 700, amule_bump 346, coverage_checks 277, template_checks 153. Files
  `src`/`tests`: 13/13, 21/23, 19/15, 11/11, 8/8.
- Module patching, `git grep -nE "monkeypatch|MonkeyPatch|mock\.patch|from unittest\.mock import.*patch" -- '*.py'`:
  133 lines in 27 files, all `monkeypatch`.
- `deprecated = true` edges in `tach.toml`, `grep -c "deprecated = true" tach.toml`: 19 (amule_bump 2,
  coverage_checks 1, p2pwatch_amule 3, vex_checks 13).
- Entry functions named `main` outside a root `__main__.py`: 10 (`boot`, `port_sync`, the four VEX checks,
  `check_templates`, `read_names`, `unit_coverage`, `bump`).
- Logic in the webui's templates, parsed with `jinja2.Environment().parse`, nodes outside text, names, attributes,
  `extends`, `block`, `include`, `for` and constants: 20 in 5 files. 8 filtered loops and their 8 one-element
  tuples, the `{% for url in (nav.prev_url,) if url %}` idiom, two per page in `files.html`, `sources.html`,
  `source_history.html` and `source_name.html`; 4 `or ""` in `node.html`.
- VEX registry: 4 premises, 2 `DeclaredMinVersion` (aMule), 2 `ModuleNotImported` (`imaplib`, `poplib`).
