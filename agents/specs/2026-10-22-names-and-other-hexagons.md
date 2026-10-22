# Post-hexagonal corrections, lot B: the names and the other hexagons

- Date: 2026-10-22. Status: approved by the operator on 2026-10-22, after Discuss and a review
  (`.reviews/lot-b-spec.md`: 1 critical, 9 major, 16 minor, all answered here), with the exemptions of blocks 16, 20
  and 22. For this lot the operator raised the ceiling to 25 blocks for the splits Act needs.
- Tier: Spec. Origin: the ledger `agents/reference/2026-10-22-post-hexagonal-audit.md`, whose decisions this lot
  applies without restating them. It fixes rows R3, R5, R8, N1 to N18 (but N12's `*Deps` and N18's
  `ObservabilityDispatcher`, D8), and, outside the crawler, H1 to H7, H10 to H15, R6b and R11. R11's rule also
  reaches the crawler's three option defaults (D14). Lot C (the crawler's design fixes) follows with its own Discuss
  and spec.
- Measured on `main` at `5adea19e` (appendix C). Paths are under `packages/<pkg>/src/<module>/` unless noted.
- What an operator sees change:
  - three SQL columns renamed (D7): `downloads.last_seen_at` and `downloads.last_progress_at` in `local.db` become
    `latest_seen_at` and `latest_progress_at`, `raw_meta` in the catalog's `observation_variants` and
    `source_variants` becomes `raw_metadata`; a console query naming them must follow;
  - the logger names follow the modules (D9): 14 of the 17 names change, four of them cited in `docs/`, and port-sync's
    s6 lines move to the supervisor's module (D19);
  - the download loop's eight "repo failure" log lines read "store failure";
  - port-sync logs a missing `amule.conf` on a line of its own instead of "amule.conf was not written (amule.conf
    does not exist)" (D20);
  - `vex_checks`' `--format` and `--output` become one `--sarif <path>` (D12); `release.yml` and `grype-scan.yml`
    follow;
  - every bump pull request's body says "the `amule_api` adapter" instead of "the `mule_api` adapter";
  - a broken template or a missing VEX input ends in a one-line error naming the file, not a traceback (D13).
  No config key, route, metric or notification changes. The `?sort=last_seen` value, the `/controls/*` routes and
  the config keys `download.output_dir` and `attr_between` keep their names (D7).

## Summary

- **Every name follows `AGENTS.md`'s Naming**: about 150 symbols, 75 files and three SQL columns renamed in one
  mechanical block, from the rename table (appendix A).
- **A Writer is always half of a store over our own state**: the SQLite adapters that serve several pairs split, the
  outputs handed to an outside consumer and the outside systems get capability names, and a rule holds the Writers'
  verbs.
- **Logger names come from the code**, so they cannot drift from their modules again.
- **The five other hexagons get their fixes**: `amule_bump`'s pure logic in its domain, boot's environment parsed
  by the composition, one way to run a command, one rule for broken inputs, typed problems.

## Conventions this lot sets

Each goes into `AGENTS.md` in the block where the whole tree first follows it.

- **C1. An adapter is named by the system, the thing and the role**: `SqliteObservationStore`,
  `GluetunForwardedPortClient`. The system is what would need another adapter if replaced: a service or a database
  (`AmuleApi`, `Github`, `Sqlite`, `S6`), a format's producer (`Syft`, `CoveragePy`, `OpenVex`), the OS beyond
  reading and writing a file (`Posix`: accounts, ownership, signals), else `Filesystem`; never a syntax (`Json`,
  `Yaml`). A brand keeps its own words' capitals (`Github` is one word, `AmuleApi` two), so its snake case follows
  them (`github`, `amule_api`). `AGENTS.md`'s "a module is the name only when it is the system" stays beside it
  (`StdlibLogger`, `ShutilFreeSpaceMeter`). Naming, block 20.
- **C2. `Reader` and `Writer` name ports over our own state only, and a `Writer` is always half of a store**: it
  has a `<Thing>Reader` that reads what it wrote, and one adapter implements one such pair. An outside system's port
  keeps a capability name (`StatusClient`, `UpstreamClient`, `ForwardedPortClient`); a port that hands an output to
  an outside consumer is named after what it does (`CodeScanningReporter`, `PullRequestDrafter`, `BumpAnnouncer`).
  Naming, block 80.
- **C3. A Writer's method starts with `record_` or `set_`**: `record_` adds a fact and leaves the earlier ones
  (observations, decisions, source points, the node id written once); `set_` replaces a current value. An ast-grep
  rule refuses any other. Naming, block 80.
- **C4. A logger is named from the code**: `StdlibLogger(<Class>.__module__)` in the composition,
  `logging.getLogger(__name__)` in an adapter; never a string literal. An ast-grep rule refuses a literal. Hard
  rules, block 24. (Corrected: block 60, since amule's three literals stay until it derives them and the rule would
  fail the gate earlier; block 24 derives the crawler's names.)
- **C5. A broken input raises; a problem is a finding on a valid input.** A tool's command line catches its domain's
  input error, prints it on one line naming the file and exits in error. Hard rules, block 72.
- **C6. A command-line option's default holds no literal**: a value the operator could set and did not is the
  domain's; a fixed value no option sets is the composition's. An ast-grep rule over every `src` refuses a
  `default=` in an `add_argument` call whose value contains a string or number literal. Hard rules, block 80.
- **C7. An adapter that runs a program receives `run_command`**, typed
  `Callable[..., subprocess.CompletedProcess[str]]` at each site, since hexagons share no module; every call passes
  `text=True`, which the annotation promises and mypy cannot check. Hard rules ("an adapter receives from the
  composition what it drives"), block 62.

## Decisions

### The names

- **D1. Every rename is in one mechanical block (20), from appendix A's table.** It holds the renames, the file moves
  they force (a port file, a double's file and a test file follow their class), the two `RENAME COLUMN` migrations
  (D7), and the places that name them (`tach.toml`, `pyproject.toml`'s TID251 paths and `tests_without_unit`, the
  ast-grep globs, `vulture_whitelist.py`, the webui's templates, the adapters' SQL, `AGENTS.md`, `docs/`), nothing
  else. A parameter, attribute or local named after a renamed class or port follows it (`repo_reader` becomes
  `upstream_client`, `reader_provider` `thread_read_connections`). Why: a rename is reviewed by its table, not file
  by file; cutting it by concept would multiply pull requests and CI runs without making it easier to read. The
  operator approves its size exemption on its row.
- **D2. The SQLite adapters split one store per pair (R3)**: `SqliteCatalogRepository` becomes
  `SqliteObservationStore`, `SqliteDecisionStore` and `SqliteCatalogScanReader`; `SqliteLocalStateRepository`
  becomes `SqliteNodeIdStore` and `SqlitePolicyFingerprintStore`. They share the connection the composition opens
  and passes to each. Why: the glossary's store is one Writer/Reader pair, and lot A already split their doubles the
  same way; their methods share no transaction (each opens its own), so the split changes no behaviour. A design
  change, not a rename: three blocks (10, 12, 14), before the mechanical one so no class is renamed twice; each new
  file takes its final name at once (`test_sqlite_decision_store_latest_decisions.py`, not `..._last_decisions.py`).
- **D3. `catalog_read.py` splits one file per reader**: `sqlite_coverage_reader.py`, `sqlite_source_reader.py`,
  `sqlite_catalog_file_reader.py`, the SQL they share in a helper module (Corrected: they share no SQL, only
  `_EPOCH`, `_MICROSECOND` and `_micros`, which each file keeps as the package's other modules do; the seeds the
  tests share move to `tests/support/catalog_seeds.py`). Why: an adapter file is its class in snake
  case (N2), and 719 lines hold three adapters. Block 16 moves the code verbatim, with its tests (1315 lines): a
  pure move, which takes the size exemption, since no cut under the bounds takes fewer than four blocks.
- **D4. `SavesRecorded` becomes a `FakeBackoffStateStore`**, a fake of the `BackoffStateWriter` /
  `BackoffStateReader` pair in `tests/fakes/adapters/driven/`. Why: it subclasses the real SQLite adapter to spy on
  it, so a step's test runs SQLite; a double of the boundary is a fake of its ports (lot A's C4). Block 10, beside
  the smallest store split.
- **D5. Outside systems and outputs get capability names (R5, C2)**: `RepoReader` becomes `UpstreamClient` (the
  domain already calls aMule's repository `UPSTREAM`); `ForwardedPortReader` becomes `ForwardedPortClient` (port-sync
  only asks gluetun whether a port was assigned, and which); `PullRequestBodyWriter` becomes `PullRequestDrafter`,
  `StepOutputWriter` `BumpAnnouncer` (it announces the new version and the body's path to whoever ran it: the
  workflow, or the terminal), and `SarifWriter` `CodeScanningReporter` (block 52, with its new argument, so its method
  is named once; Corrected: block 52 renames it, block 53 gives it `ClaimProblem`). Their `read_*` methods keep
  their names. Why: the rule C2 then holds with no exception; one common word (`Publisher`, `Exporter`) was weighed
  and refused by the operator as less telling than a name per port.
- **D6. Names decided in Discuss** (the operator): `ConsoleQueryRun` (the response model of `RunConsoleQuery`; the
  `QueryAnswer | QueryFailure` union stays unnamed, since `result` is a refused word); `SourceDisplay` (one source
  as a list shows it, built from a `KnownSource` or a `SourceNaming`: `SourceNamingDisplay` and `KnownSourceDisplay`
  did not tell at a glance what a line shows). Every other debatable name is settled by a rule or a precedent and
  listed with its reason in appendix B, for the operator to contest.
- **D7. The SQL columns follow the code; the URL, routes and config keys keep their names.** `RENAME COLUMN` renames
  `downloads.last_seen_at`, `downloads.last_progress_at` (`local/0012`) and `raw_meta` in `observation_variants` and
  `source_variants` (`catalog/0013`), and `docs/migration-4x.md` lists them beside the earlier column renames. Why:
  one concept keeps one name in every layer, the schema included; `RENAME COLUMN` rewrites no row, as
  `catalog/0012` already did, so it needs no copy first (operator, after the review found the earlier premise
  false). The `?sort=last_seen` value, the `/controls/*` routes and the keys `download.output_dir` and
  `attr_between` keep theirs, translated once by the adapter that reads them: a URL or a key change breaks the
  operator's bookmarks or files for a naming fix. The old migrations keep their SQL, which builds the old schema.
- **D8. `ObservabilityDispatcher` and the `*Deps` bags wait for lot C.** Why: lot C's A1 to A3 reshape them (the
  dispatch becomes a step, the bags lose their `shutdown` event); renamed now, they would be renamed twice.
- **D9. Logger names derived from the code (R8, C4)**, in block 24 after the renames, so each name changes once;
  amule's three in block 60, which rebuilds that wiring. `docs/migration-4x.md` and
  `docs/contributing/architecture.md` follow. Why: a literal drifts from its module at each move: 10 drifted in lot A,
  3 never named a module. `p2pwatch.observability` becomes its module's name now and changes again, by itself, with
  lot C's A3; a release between the two lots would show operators both changes, an accepted cost carried to the
  handoff's "For lot C".
- **D10. The Writers' rules (C2, C3)**: an ast-grep rule over the driven ports' files holds the verbs; two cases of
  `test_port_files.py` hold the pairs (every `<Thing>Writer` port has a `<Thing>Reader` port, and an adapter's Writer
  and Reader bases share one `<Thing>`): a test, since ast-grep reads one file at a time. Block 80, after appendix
  A's renames and block 52's. The run state's verbs come with them: `pause` and `resume` merge into
  `set_paused(paused: bool)` and `shut_down` becomes `set_shutdown_requested()`, which is no rename (two methods
  become one with a branch), so it is not block 20's.
- **D11. Local names and prose (N14, N15)**: the generic local names (`value`, `result`, `payload`, `entry`, `item`,
  `doc`, `out`, `cfg`) say what they hold; "layer" becomes "ring" where it names a ring (tach's layers keep the
  word); the stale "EC", "sync repos", "sighting", "notif" and "control" words go, and the long dashes of the files
  touched. Block 22, mechanical (165 bindings and their 503 uses in 40 files, plus the prose): its exemption covers
  the prose too, which the operator approves on its row.

### The other hexagons

- **D12. `vex_checks`' output mode is one option, `--sarif <path>`** (R11): given, the SARIF is written; absent, the
  problems are printed. `--format`, its literal default and the cross-check with `--output` go. Why: one choice, one
  option; a default for a mode no core module reads would be a domain value only the command line reads (A11's
  shape), and CI always names the mode. Block 50.
- **D13. A broken input raises, in the three tools that take one (H10, C5)**: `template_checks` (an unparsable
  template, today a problem in `logic-free` and a traceback in `template-attributes`), `vex_checks` (a missing input,
  a traceback today), `coverage_checks` (a `.coverage` without per-test contexts, today the report variant
  `NoPerTestCoverage`, which the command line already prints on one line). Each domain raises one error naming the
  file; the command line prints it and returns 1. Why: the gate fails either way, but a problem then always means a
  finding, and an error always names its file. Blocks 54, 70 and 72.
- **D14. R11's rule reaches the crawler's three option defaults** (`--config`, `--targets`, `--matcher`), fixed in
  the rule's block (80). Why: a rule that ignores one hexagon for a lot is an exception to remove later; the fix is
  one or two files.
- **D15. `amule_bump`'s pure logic goes to its domain (H1)**: `body.py` and `release.py` dissolve, their pure part
  (the changelog section, the wrapping, the version order, the diff) to `domain/`, their reads of `UpstreamClient`
  into `BumpAmule`. `difflib` and `textwrap` move from `application-imports.yml` to `domain-imports.yml`. Block 40.
- **D16. `amule_bump`'s fixed values (H6, H13, R11)**: the GitHub timeout becomes a composition constant passed to
  the adapter; one domain function makes an `ARG` line, used by the rewrite and the dry-run print; `--dockerfile`'s
  and `--body-file`'s defaults split into what the domain owns (the file names) and what `__main__` reads (the
  working and temporary directories), joined by the command line. Block 42.
- **D17. `vex_checks`' root is the working directory (H3, H11)**: `__main__` passes `cwd`, which every caller already
  runs from (poe, CI); `__file__` and the driving adapter's `.resolve()` go. The vex, template and coverage command
  lines take `PurePath`: vex's in block 50, the two others in their own blocks (70, 72), which touch them anyway.
- **D18. `vex_checks` has one problem type (H4, H5, R6b)**: `ClaimProblem(advisory_id, message)` in the domain,
  without location, for the three checks; the image and stale reports carry the VEX's location once, as the SARIF
  port already receives it; `Violation` goes, and `SarifWriter.write_violations` becomes
  `CodeScanningReporter.report_claim_problems` (D5). The bijection of `claim-coverage` moves to the domain. Why: every
  problem of a report has the same location, so the field was redundant; a stale claim contradicts no premise, so
  "violation" was wrong for it; and two adapters print the message (the command line and the SARIF), so it is worded
  once, in the domain, rather than typed per kind as R6b does for the two other tools. The glossary's `premise` and
  `claim` lines follow. Block 52 for `image-claims` and `stale-claims`, 54 for `claim-coverage` (Corrected: block 53
  for the two image checks, 54 for `claim-coverage` and the glossary).
- **D19. Boot's environment is parsed by a composition (H2, H14)**: a `BootComposition` implements `ContainerBooter`,
  parses the variables at call time and builds `BootContainer` with its settings; the command line loses `env`.
  `PosixAmuleConfStore` and `S6ServiceSupervisor` are built once in `build_command_line`, for boot and port-sync,
  the supervisor logging under its module's name (`docs/migration-4x.md` follows). Why: port-sync's composition
  already parses its own this way; parsing in `build_command_line` would refuse `port-sync` on a bad boot variable.
  Block 60, with amule's logger names (D9).
- **D20. One way to run a command (H7, H12, H6, H15, C7)**: `GrypeVulnerabilityScanner` receives `run_command`, its
  parser private and tested through `scan_sbom`; amule's two `Callable[..., object]` narrow, their calls passing
  `text=True`; the s6 stop timeout becomes a composition constant; port-sync's lifecycle reads a missing
  `amule.conf` through its own branch and log line instead of raising `FileNotFoundError` itself. Why the same
  annotation at each site rather than a shared type: hexagons never import one another, and a driven port only
  adapters consume is the shape A3 refused. Block 62.
- **D21. Typed problems in `template_checks` and `coverage_checks` (R6b)**: each kind of problem a domain type, the
  command line wording it; their reports no longer hold `tuple[str, ...]`. Blocks 70 and 74.

## Blocks

Estimates by a Sonnet agent on `main` at `5adea19e` (appendix C), counting a move as deleted and added: an upper
bound, since `git diff` detects renames. Three blocks take the size exemption, which the operator approves on their
rows: 16 moves code verbatim, 20 renames and nothing else, 22 renames local names and rewords prose. (Corrected: block 12 takes it too, approved in Act.)

| # | Branch | Holds | Lines, files (est.) |
|---|---|---|---|
| 10 | `refactor/local-state-stores` | this spec; the sizing reference's N11 bullet corrected (D7); `SqliteNodeIdStore`, `SqlitePolicyFingerprintStore` (D2); `FakeBackoffStateStore` replaces `SavesRecorded` (D4) | 290, 9 |
| 12 | `refactor/decision-store` | **exempt** (Corrected: measured at 1175 lines, 16 files; the operator approved the exemption in Act, since the decisions' code and tests move and the step tests take a `decision_store` fixture; not a pure move, the moved tests seed with `insert_file`): `SqliteDecisionStore` out of `SqliteCatalogRepository`, the guard they share in a helper module (Corrected: they share the canonical `native_id` guard, not SQL) (D2) | 400, 10 |
| 14 | `refactor/observation-store` | **exempt** (Corrected: measured at 672 lines, 15 files; the operator approved the exemption in Act, since it takes block 12's shape: the observations' code and tests move and the step tests take an `observation_store` and a `catalog_scan_reader` fixture): the rest becomes `SqliteObservationStore`, `SqliteCatalogScanReader` out of it (D2) | 450, 12 |
| 16 | `refactor/catalog-readers-split` | **exempt, a verbatim move**: `catalog_read.py` one file per reader, with its tests (D3) | 2100, 10 |
| 20 | `refactor/names` | **mechanical, exempt**: appendix A's renames, the moves they force, the two column migrations; C1 (D1, D5, D6, D7) | 3500, 200 |
| 22 | `refactor/local-names-and-prose` | **mechanical, exempt**: local names, docstrings, prose (D11) | 800, 45 |
| 24 | `refactor/logger-names-from-code` | the crawler's logger names from the code, the docs (Corrected: the ast-grep rule, its rule test and C4 move to block 60, since amule's literals would fail it here) (D9) | 150, 17 |
| 40 | `refactor/bump-domain` | `amule_bump`'s pure logic to its domain (D15) | 320, 13 |
| 42 | `refactor/bump-fixed-values` | `amule_bump`'s timeout, `ARG` line, option defaults (D16) | 150, 10 |
| 50 | `refactor/vex-root-and-sarif-option` | `vex_checks`' root from `cwd`, its `PurePath` command line, `--sarif`, the workflows (D12, D17) | 300, 13 |
| 52 | `refactor/vex-claim-problems` | `CodeScanningReporter` (Corrected: the rename only, `ClaimProblem` moved to block 53, since the whole measured 24 files) (D5) | 450, 18 |
| 53 | `refactor/claim-problem-type` | (Corrected: added, split from block 52) `ClaimProblem` for `image-claims` and `stale-claims`, the location carried once (D18) | 190, 19 |
| 54 | `refactor/vex-claim-coverage` | `claim-coverage`'s bijection in the domain, on `ClaimProblem`; vex's broken input; the glossary's `claim` and `premise` lines (Corrected: from block 52, so block 53 stays under 20 files) (D13, D18) | 400, 16 |
| 60 | `refactor/amule-boot-composition` | `BootComposition`, the adapters built once, amule's logger names (Corrected: with the ast-grep rule refusing a literal, its rule test and C4, from block 24) (D9, D19) | 400, 17 |
| 62 | `refactor/run-command` | `run_command` everywhere, the s6 timeout, the missing `amule.conf` branch; C7 (D20) | 160, 13 |
| 70 | `refactor/template-problems` | the templates' broken input, typed problems, `PurePath` (D13, D17, D21) | 300, 13 |
| 72 | `refactor/coverage-broken-input` | `NoPerTestCoverage` raised, `PurePath`; C5 (D13, D17) | 150, 7 |
| 74 | `refactor/coverage-problems` | coverage's typed problems (D21) | 400, 12 |
| 80 | `chore/naming-and-defaults-rules` | the crawler's three defaults; the run state's verbs; the option defaults' rule, the Writers' verb rule, the two pairing tests; C2, C3, C6 and the glossary (D10, D14) | 480, 16 |
| 90 | `docs/names-and-other-hexagons-wrap` | closing block: the holistic findings, backlog, handoff | 200, 6 |

- Nineteen blocks; the operator allows splits in Act up to 25 for this lot, past which the lead asks again.
- The store splits (10 to 16) come before the renames, so no class is renamed twice. The logger names (24, 60)
  follow every module rename. The rules (80) come once the tree follows them: after 20 and 52 rename the Writers,
  42 and 50 fix `amule_bump`'s and `vex_checks`' defaults.
- C1 goes into `AGENTS.md` with 20, since the renames make the tree follow it; C5 with 72, the last of the three
  tools.

## Acceptance

1. **The renames are complete**: for each class, file, module and constant of appendix A's old names, `git grep -w
   <old name> -- packages tach.toml pyproject.toml vulture_whitelist.py AGENTS.md docs` prints nothing outside the
   crawler's `migrations/` and the migration tests' SQL; for the methods, `git grep -nE
   '\.(crawl|publish|mark_seen|record_completed|save_backoff_states|write_amule_conf|write_dockerfile|write_step_outputs|write_pull_request_body|write_violations|pause|resume|shut_down)\('
   -- 'packages/*/src/**.py' 'packages/*/tests/**.py'` prints nothing. On `main` each prints at least one line.
2. **The columns follow**: a fresh `local.db` has `downloads.latest_seen_at` and `latest_progress_at`, a fresh
   catalog `observation_variants.raw_metadata` and `source_variants.raw_metadata`, and a catalog and a `local.db`
   built at the previous schema keep their rows through the migrations (the migration tests).
3. **One store per pair**: `test_port_files.py` fails on an injected adapter inheriting two Writer/Reader pairs, and
   on an injected `*Writer` port with no `*Reader` of the same thing; the tree passes. On `main` the first case
   reports `SqliteCatalogRepository` and `SqliteLocalStateRepository`.
4. **The logger names cannot drift**: an injected `StdlibLogger("p2pwatch.anything")` or `logging.getLogger("x")` in
   a `src` file fails `poe code-pattern-check`; the tree passes (on `main` the rule reports 17 sites).
5. **The Writers' verbs are held**: an injected `def write_x(self) -> None` in a Writer port fails `poe
   code-pattern-check`; the tree passes. On `main` the rule reports 11 methods.
6. **The option defaults are held**: an injected `parser.add_argument("--x", default=cwd / "y")` in a `src` file
   fails `poe code-pattern-check`, `max(xs, default=0)` and `field(default=None)` pass; the tree passes. On `main` the
   rule reports 6 sites.
7. **A broken input raises**: `python -m template_checks template-attributes <dir with {% if %}>` and `python -m
   vex_checks image-claims --sbom /nonexistent.json --vex security/crawler.vex.openvex.json` each print one line
   naming the file and exit 1, with no traceback (on `main` both print a traceback); `find_logic_constructs` returns
   no problem for a template that does not parse, and `NoPerTestCoverage` no longer exists (`git grep -w
   NoPerTestCoverage -- packages` prints nothing; on `main` it prints).
8. **Typed problems**: `git grep -nE "problems: tuple\[str" -- 'packages/*/src/**'` prints nothing (on `main`: the
   coverage and template reports); `git grep -nw "Violation\|ClaimCoverageProblem" -- packages/vex_checks` prints
   nothing.
9. **`vex_checks` runs from the root**: `__main__.py` holds no `__file__`; `git grep -n "\.resolve()" --
   'packages/*/src/*/adapters/driving/**'` prints nothing; `uv run poe vex-claim-coverage` passes.
10. **`amule_bump`'s domain and values**: `application/use_cases/body.py` and `release.py` no longer exist;
    `git grep -n "import difflib\|import textwrap" -- packages/amule_bump/src/amule_bump/domain` prints two lines;
    `git grep -nE 'timeout=30|"60000"' -- 'packages/*/src/*/adapters/**'` prints nothing.
11. **Boot's environment**: `ContainerBooter.boot_container` takes no argument; `PosixAmuleConfStore(` and
    `S6ServiceSupervisor(` each appear once in `p2pwatch_amule`'s `composition/` (twice on `main`).
12. **One way to run a command**: `git grep -n "subprocess.run(" -- 'packages/*/src/*/adapters/**'` and `git grep -n
    "run_command: Callable\[\.\.\., object\]" -- 'packages/*/src/**'` print nothing (one and two lines on `main`).
13. **The doubles and splits**: `SavesRecorded` and `catalog_read.py` no longer exist, and `test_search_tasks.py`
    opens no `local.db` (`git grep -n "open_local\|SavesRecorded" --
    packages/crawler/tests/application/steps/test_search_tasks.py` prints nothing); the catalog fixture stays, as in
    the other step tests. (Corrected: the check named every SQLite connection, which D4 does not decide; operator,
    block 10.)
14. **The workflows still run**: before the merge, `gh workflow run grype-scan.yml --ref <top branch>` passes, and
    release's `image-claims` command, run from the root with `--sarif` against a Syft SBOM of the crawler's image,
    exits 0.
15. **Nothing out of scope changes**: no change under `deploy/`, `security/`, `packages/amule/docker/` and the
    Dockerfiles; the crawler's `migrations/` gains only `catalog/0013` and `local/0012`; `.github/workflows/` changes
    only `--format`/`--output` to `--sarif` (D12).
16. **The gate is green** at every block.

## Backlog

- **A copy before a migration that rewrites rows** stays open and ships before the next release; this lot's column
  renames rewrite no row (D7). This lot changes the image's code, so a release may follow, after that copy.
- **Contract tests for the fakes** stays open and follows lot C, which settles the ports' final shape.
- **The ast-grep rule tests bound to their rules by design** stays open: this lot adds three rules with their tests,
  the existing way.
- **Sort the files view by first seen** stays open; it will add a `first_seen` sort value beside `last_seen`, which
  this lot keeps (D7).
- **The Grype scan back on p2pwatch at the v5 release** stays open: this lot only changes the option its steps pass
  (D12), not its legs.
- **Multi network, stage 5**, **The webui in the visitor's time zone**, **The VEX's Python claims applied by Grype**,
  **The metrics served by the webui on 8080**, **Every stamp an integer of microseconds**, **Adopt ty**, **Test
  quality**, **Mutation testing in the gate** and **The node page shows a node id set in `crawler.yml`** stay open:
  none touches what this lot changes.

## Appendix A: the rename table

Kinds: P port, M port method, A adapter, D domain type or function, R response model, V webui display, F double,
f module file or directory, n name (parameter, attribute, local, constant, field), c SQL column. A file follows its
class, and a name follows the class or port it is named after (D1), unless a row says otherwise.

### Stores and ports (R3, R5, N5, N6, N8, N17)

| Old | New | Kind |
|---|---|---|
| `SqliteBackoffStateRepository` | `SqliteBackoffStateStore` | A |
| `SqliteSourceRepository` | `SqliteSourcePointStore` | A |
| `SqliteDownloadRepository` | `SqliteTrackedDownloadStore` | A |
| `PosixAmuleConf` | `PosixAmuleConfStore` | A |
| `FilesystemDockerfile` | `FilesystemDockerfileStore` | A |
| `AsyncioRunState` | `AsyncioRunStateStore` | A |
| `InMemoryStatusBoard`, `status_board`, `board` | `InMemoryStatusReadingStore`, `status_reading_store` | A, n |
| `repository` (the stores' tests) | the store's name (`observation_store`, ...) | n |
| `RepositoryError`, `domain/repository_errors.py` | `StoreError`, `domain/store_error.py` | D, f |
| `ClientStatusWriter`, `ClientStatusReader` | `StatusReadingWriter`, `StatusReadingReader` | P |
| `ClientStatusWriter.publish` | `set_reading` | M |
| `FakeClientStatusStore` | `FakeStatusReadingStore` | F |
| `DownloadWriter`, `DownloadReader` | `TrackedDownloadWriter`, `TrackedDownloadReader` | P |
| `DownloadWriter.mark_seen`, `.record_completed` | `set_seen`, `set_completed` | M |
| `FakeDownloadStore`, its `fail_active_states` | `FakeTrackedDownloadStore`, `fail_tracked_states` | F, n |
| `BackoffStateWriter.save_backoff_states` | `set_backoff_states` | M |
| `AmuleConfWriter.write_amule_conf` | `set_amule_conf` | M |
| `DockerfileWriter.write_dockerfile` | `set_dockerfile` | M |
| `RepoReader`, `GitHubRepoReader`, `FakeRepoReader` | `UpstreamClient`, `GithubUpstreamClient`, `FakeUpstreamClient` | P, A, F |
| `ForwardedPortReader`, `GluetunForwardedPortReader`, `FakeForwardedPortReader` | `ForwardedPortClient`, `GluetunForwardedPortClient`, `FakeForwardedPortClient` | P, A, F |
| `PullRequestBodyWriter.write_pull_request_body`, `FilesystemPullRequestBodyWriter` | `PullRequestDrafter.draft_pull_request_body`, `FilesystemPullRequestDrafter` | P, M, A |
| `StepOutputWriter.write_step_outputs`, `GitHubStepOutputWriter`, `TerminalStepOutputWriter` | `BumpAnnouncer.announce_bump`, `GithubActionsBumpAnnouncer`, `TerminalBumpAnnouncer` | P, M, A |
| `AccountManager`, `PosixAccountManager` | `AccountProvisioner`, `PosixAccountProvisioner` | P, A |

The doubles of every renamed port follow it (`Fake<NewName>`). `SarifWriter` is block 52's (D18); `RunStateWriter`'s
verbs block 80's (D10).

### Adapters and files (N1 to N4, N18)

| Old | New | Kind |
|---|---|---|
| `adapters/driven/wall_clock_system.py`, `monotonic_clock_asyncio.py` | `system_wall_clock.py`, `asyncio_monotonic_clock.py` | f |
| `adapters/driven/mule_api/`, its `client.py` | `adapters/driven/amule_api/`, `amule_api_client.py` | f |
| `persistence_sqlite/*_repository.py` | the store's name in snake case | f |
| `persistence_sqlite/local_read.py` | `sqlite_node_state_reader.py` | f |
| `ReaderProvider`, `persistence_sqlite/reader.py` | `ThreadReadConnections`, `thread_read_connections.py` | n, f |
| `JsonVexReader` | `OpenVexReader` | A |
| `YamlConfigChecker` | `FilesystemConfigChecker` | A |
| `CoveragePyReader` | `CoveragePyTestCoverageReader` | A |
| `FakeGitHubServer` (`fake_git_hub_server.py`) | `FakeGithubServer` (`fake_github_server.py`) | F |

### Doubles (N10)

`BlockingMonotonicClock` → `FakeBlockingMonotonicClock`; `BrokenDisk` → `FakeBrokenFreeSpaceMeter`;
`HangingNotifier` → `FakeHangingNotifier`; `ImmediateLoop` → `FakeImmediateEventLoop`; `LaggingDownloadStore` →
`FakeLaggingTrackedDownloadStore`; `LoopMonotonicClock` → `FakeLoopMonotonicClock`; `LoopWallClock` →
`FakeLoopWallClock`; `NeverSuspends` → `FakeNeverSuspendingSearchClient`; `NoSetStateStore` →
`FakeNoSetStateTrackedDownloadStore`; `NotificationSink` → `FakeNotificationSink`; `RaisingNotifier` →
`FakeRaisingNotifier`; `RecordingLoop` → `FakeRecordingEventLoop`; `RecordingNotifier` → `FakeNotifier`;
`ScriptedClient` → `FakeStatusClient`; `ShutDownServer` → `FakeMetricsServer`; `ShutdownDuringCycleCatalog` →
`FakeShutdownDuringCycleDecisionReader`; `SteppedClient` → `FakeSteppedStatusClient`; `ThreadRecordingContext` →
`FakeServingResource`; `TickingMonotonicClock` → `FakeTickingMonotonicClock`; `TickingWallClock` →
`FakeTickingWallClock`; `TimedClient` → `FakeTimedSearchClient`; `TimedEventEmitter` → `FakeTimedEventEmitter`.
(`SavesRecorded` is D4's.)

### Displays and response models (N7, N16)

| Old | New | Kind |
|---|---|---|
| `TimelineRowDisplay` | `ObservationDisplay` | V |
| `BackoffEntryDisplay` | `BackoffStateDisplay` | V |
| `FileRowDisplay` | `CatalogEntryDisplay` | V |
| `SourceHistoryRowDisplay` | `SharingPeriodDisplay` | V |
| `SourceListRowDisplay` | `SourceDisplay` | V |
| `SourceFileRowDisplay`, its fields `file`, `history` | `FileSharingPeriodDisplay`, `filename`, `sharing_period` | V, n |
| `ConsoleQueryOutcome` | `ConsoleQueryRun` | R |
| `CrawlerRunner.crawl` | `run_crawler` | M |

The `app.py` helpers building them follow. The glossary's `status reading` line follows `InMemoryStatusReadingStore`
(block 20).

### `latest`, abbreviations, `native_id` (N11 to N13)

| Old | New | Kind |
|---|---|---|
| `downloads.last_seen_at`, `downloads.last_progress_at` (`local/0012`) | `latest_seen_at`, `latest_progress_at` | c |
| `raw_meta` in `observation_variants`, `source_variants` (`catalog/0013`) | `raw_metadata` | c |
| `read_last_seen_at_by_file`, `last_seen_at_by_file`, `_LAST_SEEN_AT_BY_FILE` | `read_latest_seen_at_by_file`, `latest_seen_at_by_file`, `_LATEST_SEEN_AT_BY_FILE` | M, n |
| `KnownSource.last_seen_at`, `SourceNaming.last_seen_at` | `latest_seen_at` | n |
| `TrackedDownload.last_progress_at` | `latest_progress_at` | n |
| `_SELECT_LAST_DECISIONS` | `_SELECT_LATEST_DECISIONS` | n |
| `CatalogEntrySort.LAST_SEEN` (value `"last_seen"` kept) | `LATEST_SEEN` | n |
| display fields `last_seen_display`, `last_seen`, `last_progress_at` (not a sharing period's `first_seen`/`last_seen`) | `latest_seen_display`, `latest_seen`, `latest_progress_at` | n |
| `conn` (tests) | `connection` | n |
| `catalog_repo`, `local_repo`, `source_repo`, `download_repo` | the stores' names | n |
| log text "repo failure" | "store failure" | n |
| `repo_root` (`vex_checks`; gone with D17 where it was the root) | `repository_root` | n |
| `templates_dir`, `static_dir`, `webui_pkg_dir` | `templates_directory`, `static_directory`, `webui_package_directory` | n |
| `DownloadConfig.output_dir`, `DEFAULT_OUTPUT_DIR` (key `download.output_dir` kept) | `output_directory`, `DEFAULT_OUTPUT_DIRECTORY` | n |
| `INCOMING_DIR`, `TEMP_DIR` | `INCOMING_DIRECTORY`, `TEMP_DIRECTORY` | n |
| `KeywordDef`, `RegexDef`, `CoverageDef`, `AttrBetweenDef`, `AllDef`, `AnyDef`, `NotDef`, `TokenDef`, `TokenRef` | `KeywordDefinition`, `RegexDefinition`, `CoverageDefinition`, `AttributeBetweenDefinition`, `AllDefinition`, `AnyDefinition`, `NotDefinition`, `TokenDefinition`, `TokenReference` | D |
| `AttrBetweenMatcher` (key `attr_between` kept) | `AttributeBetweenMatcher` | D |
| `SourceMeta`, `RawMeta`, `fold_raw_meta`, `_source_meta`, field `raw_meta` | `SourceMetadata`, `RawMetadata`, `fold_raw_metadata`, `_source_metadata`, `raw_metadata` | D, n |
| `ed2k_hash` in Python (not in the old schema's SQL), `build_ed2k_link`'s `ed2k_hash` | `native_id` | n |

## Appendix B: names settled by a rule or a precedent

Each was weighed against one alternative; the operator may contest any.

| Name | Alternative | Why |
|---|---|---|
| `PersistenceError` kept | `SqliteStoreError` | internal to the adapter, as `ApiError` |
| `UpstreamClient.read_*`, `read_forwarded_port` kept | drop `read_` | no rule asks a client's methods to change |
| `OpenVexReader` | `FilesystemVexReader` | OpenVex is a format's producer, the ledger's own example (C1) |
| `Github*` | `GitHub*` | one brand word, so one snake case word; `fake_git_hub_server.py` was the symptom |
| `StatusReadingWriter` / `Reader` | `StatusBoardWriter` / `Reader` | a pair is named after the thing stored, as `SourcePointWriter` |
| `PublishedReading`, `published_at` kept | `StoredReading`, `stored_at` | a reading as its readers find it, with the instant it became theirs |
| `TrackedDownloadWriter` / `Reader` | keep `Download*` | the glossary's `tracked` and `TrackedDownload` |
| `FileSharingPeriodDisplay` | `SharingPeriodWithFileDisplay` | a sharing period shown with its file |
| `FakeImmediateEventLoop`, `FakeRecordingEventLoop` | `...Loop` | they replace an event loop |
| `FakeNotifier` | `FakeRecordingNotifier` | the plain recording fake, as `FakeEventEmitter` |
| `FakeStatusClient` | `FakeScriptedStatusClient` | the only fake of `StatusClient` |
| `FakeMetricsServer`, `FakeServingResource` | `FakeShutDownServer`, `FakeThreadRecordingContext` | named after what they replace |
| `FakeBrokenFreeSpaceMeter` | a knob on `FakeFreeSpaceMeter` | a rename, in the mechanical block |
| `set_seen`, `set_completed` | `set_listed_statuses`, keep `record_completed` | both replace a value of the row (C3) |
| `set_paused(paused)`, `set_shutdown_requested()` | `set_searching`, `set_idle`, `set_shutting_down` | the reader already asks `is_paused` |
| `INCOMING_DIRECTORY`, `TEMP_DIRECTORY` | keep, as `amule.conf`'s keys | they hold paths, not the keys |
| `*Definition`, `TokenReference` | `*Spec` | no abbreviation; "spec" is another word |
| `build_ed2k_link(..., native_id)` | keep `ed2k_hash` | it is the file's `native_id` |
| `run_crawler` | keep `crawl` | verb and object, as `run_port_sync_loop` |
| `ThreadReadConnections` | `ReadOnlyConnectionSource` | one read-only connection per thread; a helper, not an adapter, so no system prefix |
| `AccountProvisioner` | keep `AccountManager` | named after its action, `find_or_create_amule_account` |
| `CodeScanningReporter`, `PullRequestDrafter`, `BumpAnnouncer` | `*Publisher`, `*Exporter` | the operator, D5 |

## Appendix C: measurements

Taken on `main` at `5adea19e` on 2026-10-22 by two Opus inventory agents and the spec's review (reports in the
lead's scratchpad and `.reviews/lot-b-spec.md`). Re-run before acting on one.

- Rename union: 195 code and config files, 3 in `docs/` and `AGENTS.md` (`git grep -lw` over appendix A's old
  class, file and constant names, the columns and generic words excluded); about 75 file moves.
- Local names (D11): 165 bindings of `value`, `result`, `payload`, `entry`, `item`, `doc`, `out`, `cfg`, 503 uses,
  40 files (an AST scan, `.reviews/` scratch script).
- Logger literals in `src`: 17, of which 13 name no module (`git grep -nE "StdlibLogger\(|getLogger\(" --
  'packages/*/src/**.py'`, one literal split over two lines); four cited in `docs/` (`migration-4x.md` three,
  `architecture.md` one).
- Writer methods starting with neither `record_` nor `set_`: 11 in 9 ports, 3 of them on Writers without a Reader.
- `default=` holding a literal in `add_argument`: 6 (the crawler 3, `amule_bump` 2, `vex_checks` 1), prototype
  ast-grep rule in the lead's scratchpad (`default-rule/rule2.yml`).
- `catalog_read.py` 719 lines, its tests 1315; `catalog_repository.py` 248; `local_state_repository.py` 74.
- Current schema (fresh `open_catalog`, `open_local`): `raw_meta` in `observation_variants` and `source_variants`,
  `last_seen_at` and `last_progress_at` in `downloads`; no `ed2k_hash` column.
- Block estimates: a Sonnet agent from the files each row touches (`lot-b-estimates.md` in the lead's scratchpad),
  a move counted as deleted and added.
