# Handoff: the names and the other hexagons, lot B of the post-hexagonal corrections

Drafted by block 80 from the lot's block reports (#410, #411, #413 to #429) and its own, and from the lead's notes
taken during Act; corrected by the closing block 90 with the holistic review (`.reviews/lot-b-holistic.md` and
`.reviews/lot-b-holistic-subreviews.md`).

## State

Tier Spec lot. Spec `agents/specs/2026-10-22-names-and-other-hexagons.md` (approved 2026-10-22, with the exemptions
of blocks 16, 20 and 22; the operator raised the lot's ceiling to 25 blocks for the splits Act needs). It applies the
ledger `agents/reference/2026-10-22-post-hexagonal-audit.md`'s rows R3, R5, R8, N1 to N18 (but N12's `*Deps` and
N18's `ObservabilityDispatcher`, D8), and, outside the crawler, H1 to H7, H10 to H15, R6b and R11; R11's rule also
reaches the crawler's three option defaults (D14). Lot C (the crawler's design fixes) follows with its own Discuss and
spec.

One stack cut from `main` at `5adea19e`. Twenty-three blocks, the closing ones included: the spec's nineteen, block 52
split in Act into 52 and 53 (file bound), block 60 into 60 and 61 (file bound), the closing block cut by the lead into
90, 92 and 94 (its commits measured 1082 lines in 75 files together).

| Block | Pull request | Branch |
|---|---|---|
| 10 | #410 | `refactor/local-state-stores` |
| 12 | #411 | `refactor/decision-store` |
| 14 | #413 | `refactor/observation-store` |
| 16 | #414 | `refactor/catalog-readers-split` |
| 20 | #415 | `refactor/names` |
| 22 | #416 | `refactor/local-names-and-prose` |
| 24 | #417 | `refactor/logger-names-from-code` |
| 40 | #418 | `refactor/bump-domain` |
| 42 | #419 | `refactor/bump-fixed-values` |
| 50 | #420 | `refactor/vex-root-and-sarif-option` |
| 52 | #421 | `refactor/vex-claim-problems` |
| 53 | #422 | `refactor/claim-problem-type` |
| 54 | #423 | `refactor/vex-claim-coverage` |
| 60 | #424 | `refactor/amule-boot-composition` |
| 61 | #425 | `chore/logger-name-rule` |
| 62 | #426 | `refactor/run-command` |
| 70 | #427 | `refactor/template-problems` |
| 72 | #428 | `refactor/coverage-broken-input` |
| 74 | #429 | `refactor/coverage-problems` |
| 80 | #430 | `chore/naming-and-defaults-rules` |
| 90 | closing, part 1 | `docs/names-and-other-hexagons-wrap` |
| 92 | closing, part 2 | `fix/broken-inputs-one-line` |
| 94 | closing, part 3 | `refactor/review-findings` |

Not merged at writing. The lot changes the image's code (the logger names, the columns, the log lines), so a release
may follow, after "A copy before a migration that rewrites rows" ships ("Backlog", below).

## What was built

- **One store per pair** (blocks 10 to 16, D2 to D4): `SqliteCatalogRepository` became `SqliteObservationStore`,
  `SqliteDecisionStore` and `SqliteCatalogScanReader`; `SqliteLocalStateRepository` became `SqliteNodeIdStore` and
  `SqlitePolicyFingerprintStore`, all on the connection the composition opens. The decision store's canonical
  `native_id` guard is in `canonical_native_id.py`. `catalog_read.py` split verbatim into
  `sqlite_coverage_reader.py`, `sqlite_source_reader.py`, `sqlite_catalog_file_reader.py`, the tests' seeds in
  `tests/support/catalog_seeds.py`. `FakeBackoffStateStore` replaced `SavesRecorded`.
- **Every name follows Naming** (block 20, D1, D5 to D7): appendix A's renames and the file moves they force; the
  migrations `catalog/0013` (`raw_meta` to `raw_metadata`) and `local/0012` (`latest_seen_at`,
  `latest_progress_at`); C1 in `AGENTS.md`. The SQL function `fold_raw_meta` keeps its name, since `catalog/0007`
  calls it.
- **Local names and prose** (block 22, D11): the generic locals named after what they hold, "ring" where a ring is
  meant, the stale words gone; `.gitignore` gains `.coverage.*`.
- **Logger names from the code** (blocks 24, 60, 61, D9, C4): `StdlibLogger(<Class>.__module__)` and
  `logging.getLogger(__name__)`; the rule `no-literal-logger-name` refuses a literal in every `src`.
- **`amule_bump`** (blocks 40, 42, D15, D16): the changelog section, the wrapping, the version order, the diff, the
  tag checks (`check_release_tag`, `tagged_commit_id`) in `domain/`, the reads in `BumpAmule`; the GitHub timeout a
  composition constant; one function makes an `ARG` line; `DOCKERFILE_PATH` and `PULL_REQUEST_BODY_FILENAME` the
  domain's, the directories `__main__`'s.
- **`vex_checks`** (blocks 50 to 54, D12, D13, D17, D18): the root is the working directory; `--sarif <path>`
  replaces `--format` and `--output`, both workflows following; `SarifWriter` became `CodeScanningReporter`
  (`report_claim_problems`), `Violation` and `ClaimCoverageProblem` became one `ClaimProblem`, the location carried
  once by the reports; `evaluate_claim_coverage` holds the bijection in the domain; a missing input raises
  `BrokenInputError`, printed on one line.
- **`p2pwatch_amule`** (blocks 60, 62, D19, D20, C7): `BootComposition` implements `ContainerBooter` and parses the
  variables at call time through `parse_boot_settings` (`BootSettings.port_sync_enabled`); `PosixAmuleConfStore` and
  `S6ServiceSupervisor` built once; `run_command` typed `Callable[..., subprocess.CompletedProcess[str]]` with
  `text=True` at every call, Grype included; the s6 stop timeout a composition constant (`stop_timeout_seconds`); a
  missing `amule.conf` has its own branch and line at both of port-sync's reads.
- **`template_checks`, `coverage_checks`** (blocks 70 to 74, D13, D17, D21, C5): a broken input raises
  `BrokenInputError`, the command line prints it on one line and exits 1; the problems are domain types
  (`RefusedNode`, `FilteredLoop`; `ListingWithoutReason`, `StaleListing`, `UnitNameCollision`, `ListedTestOfModule`,
  `UnmappedTestFile`, `Shortfall`), worded by the command line; `NoPerTestCoverage` is gone.
- **The rules** (block 80, D10, D14, C2, C3, C6): the run state's Writer is `set_paused(paused)` and
  `set_shutdown_requested()`; the crawler's `--config`, `--targets` and `--matcher` defaults are the domain's
  (`DEFAULT_CONFIG_PATH`, `DEFAULT_TARGETS_PATH`, `DEFAULT_MATCHER_PATH` in `config_defaults.py`); the ast-grep rules
  `writer-verbs` and `no-literal-option-default`; `test_port_files.py`'s two pair checks; C2, C3, C6 and the
  glossary's `record`, `set` and `run state` lines in `AGENTS.md`.

## What an operator sees change

As the spec lists it: the three columns renamed (a console query naming them follows); 14 of the 17 logger names, and
port-sync's s6 lines under the supervisor's module; "repo failure" reads "store failure"; port-sync's missing
`amule.conf` on lines of its own, at both reads (block 62, `docs/troubleshooting.md`); `vex_checks`' `--sarif`; the
bump body's "the `amule_api` adapter"; a broken template, VEX input, Grype run, `pyproject.toml` or `.coverage` on
one line naming the file (closing block: every shape, not only an absent file); `poe template-check`'s lines name each
template by its path under the directory given (closing block). No config key, route, metric or notification
changes.

## Acceptance

From the block reports, re-run where noted.

1. Block 20: every old class, file, module and constant prints nothing outside `migrations/` and the old-schema SQL,
   but `fold_raw_meta` (kept, `catalog/0007` calls it: a correction Acceptance 1 needs). Block 80: the method regex
   prints nothing at `77aa8b67`.
2. Block 20: the two migration tests, written first (`assert 12 == 13`, `assert 11 == 12`).
3. Block 80: on `5adea19e` (the test file copied into a worktree) the port check reports `PullRequestBodyWriter`,
   `SarifWriter`, `StepOutputWriter`, the class check `SqliteCatalogRepository: ['CatalogScan', 'Decision',
   'Observation']` and `SqliteLocalStateRepository: ['NodeId', 'PolicyFingerprint']`; on the tree an injected
   `OrphanWriter` and a `TwoPairsStore(ObservationWriter, DecisionReader)` each fail; the tree passes.
4. Block 61: an injected `StdlibLogger("p2pwatch.anything")` and `logging.getLogger("x")`, with the parent's three
   amule literals, give 5 sites; the tree passes. The "17 on `main`" was not re-measured.
5. Block 80: `writer-verbs` reports 11 methods on `5adea19e`, 3 on its parent (`RunStateWriter`), an injected
   `def write_x` on the tree; the tree passes.
6. Block 80: `no-literal-option-default` reports 6 sites on `5adea19e`, 3 on its parent (the crawler's); an
   injected `parser.add_argument("--x", default=cwd / "y")` is reported, `max(xs, default=0)` and
   `field(default=None)` beside it are not; the tree passes.
7. Blocks 54, 70, 72: `image-claims --sbom /nonexistent.json` prints `error: /nonexistent.json: no such file`, exit
   1; a template with `{% if %}` `error: 404.html:8: Expected an expression, got 'end of statement block'`, exit 1;
   `git grep -w NoPerTestCoverage -- packages` prints nothing.
8. Blocks 53, 54, 74: `problems: tuple[str` prints nothing; `Violation\|ClaimCoverageProblem` prints nothing in
   `vex_checks`.
9. Block 50: no `Path(__file__)` nor `.resolve()` in `vex_checks`' `src` and the driving adapters;
   `poe vex-claim-coverage` exits 0.
10. Blocks 40, 42, 62: `body.py`, `release.py` gone; two `import difflib\|import textwrap` lines in the domain;
    `timeout=30|"60000"` prints nothing in the adapters.
11. Block 60: `boot_container` takes no argument; one `PosixAmuleConfStore(` and one `S6ServiceSupervisor(` in
    amule's `composition/`.
12. Block 62: no `subprocess.run(` in the adapters, no `Callable[..., object]` `run_command`.
13. Block 10: as corrected (operator, "B"), `open_local\|SavesRecorded` prints nothing in `test_search_tasks.py`.
14. Block 50, local half: release's `image-claims` from the root exits 0 on a Syft SBOM of
    `ghcr.io/mission-titar/p2pwatch:main`, with and without `--sarif`. The lead's, after the top is pushed:
    `gh workflow run grype-scan.yml --ref <top branch>`: (to be filled by the lead: run id and conclusion).
15. Block 80, at `77aa8b67`: `git diff --stat 5adea19e` over `deploy`, `security`, `packages/amule/docker` and both
    Dockerfiles prints nothing; `.github/workflows/` changes only the `--sarif` lines; the migrations gain only
    `catalog/0013_raw_metadata.sql` and `local/0012_latest_columns.sql`.
16. The gate green at every block (each report); CI green on every block's head, one run each, 10 to 74 (`gh run
    list`, 2026-10-23).

## Holistic review

`.reviews/lot-b-holistic.md`: 0 critical, 3 major, 17 minor; its two sub-reviews (stores, renames) add the minors
of `.reviews/lot-b-holistic-subreviews.md`. Every finding is fixed in the closing blocks 90 to 94 (the default exit), but
Acceptance 14, the lead's. Exits, finding by finding:

- **C5 gaps** (major): fixed. The three vex readers refuse a directory, an unreadable file, a file not in UTF-8, not
  JSON or not of their format; Grype's non-zero exit names the SBOM (`grype exited with status N`), and so does an
  output that is not its JSON report; `coverage_checks` refuses a `pyproject.toml` key that is not a table, naming
  the key. One failing test per shape first (32 in `vex_checks`, 3 in `coverage_checks`: `IsADirectoryError`,
  `UnicodeDecodeError`, `KeyError: 'statements'`, `TypeError: 'int' object is not iterable`, `AttributeError: 'str'
  object has no attribute 'get'` and the others).
- **The docs naming the old columns** (major): fixed, `docs/troubleshooting.md` and `docs/contributing/architecture.md`
  name `latest_seen_at` and `raw_metadata`; the history of `local/0005` and `catalog/0007` keeps the old names.
- **Acceptance 14** (major): the lead's, after the top is pushed (Acceptance, above).
- **The ast-grep rules see a literal in the call only**: fixed as decided. `no-literal-option-default` also refuses a
  literal in `set_defaults` (its test failed first, `FAIL no-literal-option-default ..............MM`); both rules'
  notes and `AGENTS.md` say an indirection is a review matter.
- **A Writer-only class passes the class check**: fixed, `test_port_files.py` refuses a class implementing a
  `<Thing>Writer` port without its `<Thing>Reader`; injected on `AsyncioRunStateStore`, it reported
  `{'...asyncio_run_state_store.py::AsyncioRunStateStore': ['RunStateWriter']}`.
- **C2's clause**: fixed in `AGENTS.md`, "`Reader` and `Writer` name ports over our own state only (databases, files,
  memory)", so `SbomReader` and `TestCoverageReader`, which read files, follow it; no rename.
- **`RunStateReader` and `set_shutdown_requested`**: named as the rule's one exception in `AGENTS.md`, ended by lot
  C's A1.
- **The template parse error relative to the directory**: fixed, `FilesystemTemplateReader` keys each template by its
  path under the directory given, so its problems and errors all name the file that way (the reader's test failed
  first, `PosixPath('base.html') != PosixPath('/tmp/.../base.html')`).
- **The stores' prose** (`store_error.py`, `errors.py`, `connection.py`, `__init__.py`, `AGENTS.md`'s "sync repos",
  architecture's "repos", `output_dir`, the double plural): fixed.
- **`catalog_seeds.py` at the `tests/support` root, its `h`**: fixed, moved to
  `tests/support/adapters/driven/persistence_sqlite/`, the local named `native_id`.
- **A package with no module passes whatever its `.coverage`**: fixed, not accepted. `TestCoverageReader` became
  `read_test_coverage_by_module`, which loads the run before any module, and `CheckUnitCoverage` calls it once,
  whatever the module count (the use case's test on an empty package and the reader's on an absent data file with no
  module failed first).
- **The logger names a wrong class would pass**: the re-evaluation's is tested, a wiring test seeding 200 files to
  read its progress line under `p2pwatch.application.steps.reevaluate_catalog` (mutated to
  `reevaluate_if_policy_changed.__module__`, it failed). `SearchTaskRunner` and `record_observation` log only on a
  `StoreError`, which no wiring test can provoke: "Not validated". The s6 supervisor's (operator: "A"): it logs
  through `logging.getLogger(__name__)`, its `Logger` parameter gone, so no wiring can give it another name; its
  tests read the record's name (`TypeError: ... missing 1 required keyword-only argument: 'logger'` first).
- **`docs/migration-4x.md`'s long line**: fixed.
- **The names that did not follow their class** (D1): fixed, from the symbols with Serena (the functions, the module
  constants, the test names) and the locals with a token-level script, each batch checked with `git diff
  --word-diff`: `console_query_run`, `_CONSOLE_QUERY_RUN`; `_parse_token_reference`, `_parse_token_definition`,
  `_definition_token_names`, `_operand_token_references`, `_build_definition`, `token_definition`, `token_names`,
  `token_references`; `amule_conf_store`, `dockerfile_store`, `run_state_store`, `_amule_conf_store`;
  `thread_read_connections`; the test names after `announce_bump`, `draft_pull_request_body`, `StoreError` and
  "store failure"; `_INCOMING_DIRECTORY`, `_STATE_DIRECTORY`, `_STATE_SUBDIRECTORIES`, `ed2k_directory`; one
  `tracked_download_store` in `test_run_download_cycle.py` (its fixture `real_tracked_download_store`),
  `status_reading_store`; `_latest_seen`, `_raw_metadata` and the `last_seen` test names.
- **The stale prose beyond the store words** (`format.py`, `test_format.py`, `ed2k_link.py`'s `EC_OP_ADD_LINK` and long
  dash, the fake's `EC_OP_FAILED`, "DB conns"): fixed.
- **The migration history without `catalog/0013` and `local/0012`**: fixed, one sentence.
- **`LATEST_SEEN = "last_seen"` and `fold_raw_meta` without a reason**: fixed, one comment line each.
- **Acceptance 13's `catalog` fixture, "Nineteen blocks", Acceptance 1's `fold_raw_meta`, D17 for coverage, the
  first read's log line**: each corrected in the spec with `(Corrected: ...)`.
- **The type names blocks 70 and 74 chose** (the lead's note): checked against Naming, kept. Each names what one
  instance is, with no abbreviation: `RefusedNode`, `FilteredLoop`, `LogicConstruct`; `ListingWithoutReason`,
  `UnitNameCollision`, `ListedTestOfModule`, `UnmappedTestFile`, `StaleListing`, `Shortfall`.

## Departures from the spec

- Block 10: Acceptance 13 narrowed to `local.db` (class 2, below).
- Block 12: the decision and observation stores share the `native_id` guard, not SQL (D2's row corrected); the moved
  files and tests took their final names (`_SELECT_LATEST_DECISIONS`, `test_latest_decisions_*`).
- Block 14: the step tests' fixtures `observation_store` and `catalog_scan_reader`; exemption approved in Act.
- Block 16: no helper module, the readers share no SQL (D3 corrected); the seeds public in `tests/support/`.
- Block 20: the SQL aliases feeding `KnownSource` and `SourceNaming` are `latest_seen_at`, a sharing period keeps
  `first_seen_at` and `last_seen_at`; the `app.py` helpers and the fake's knobs follow their renames.
- Block 22: D11's word list taken with `data` and `obj` too; `HiddenInputDisplay.value`, `DbOptionDisplay.value`, the
  real "EC" and the `/controls/*` names kept.
- Block 24: the rule, its test and C4 moved to block 61 (rows 24, 60, C4 corrected).
- Block 40: the tag checks moved to the domain too, so `BumpError` comes from one ring.
- Block 50: a relative VEX with `..` is no longer normalised in a problem's location.
- Blocks 52, 53, 54: the rename alone in 52, `ClaimProblem` in 53, the glossary's `claim` and `premise` in 54
  (rows and D5, D18 corrected). Block 54: the source rule reader's id check raises `BrokenInputError` too; the
  scanner checks the SBOM exists before running Grype; only `FileNotFoundError` is translated (below).
- Block 60: the variables parsed through the domain's `parse_boot_settings` (D19 corrected); `BootContainer` still
  implements `ContainerBooter`, so its double sits in `tests/fakes/composition/`.
- Block 61: split from 60.
- Block 62: port-sync's first read of a missing `amule.conf` gets its line too (H15); `vex_checks` gains its own
  `FakeCommandRunner`; the stop timeout an `int` of seconds.
- Block 72: coverage's command line holds no path at all, rather than a `PurePath` (D17); C5 placed after the
  domain's-value rule.
- Block 80: `FakeRunStateStore` reads back what it was set to, a store, where it kept a list of method names; the
  three defaults in `config_defaults.py`, its docstring widened, rather than a new module; `_under_cwd` takes
  `str | PurePath`. The class check reads a class's direct bases imported from an `application.ports` module, not
  through an intermediate class as `test_fake_files.py` does.

## Class 1 fixes

- Block 10: the fingerprint tests' stale `last_backfill_policy` wording; the stores' comments.
- Block 12: the moved "unknown hash" test reads a key never stored.
- Block 14: three docstrings' "catalog repo".
- Block 22, from block 20's leftovers: `reader_provider` to `thread_read_connections`, the composition's connections
  and `backoff_state_store`, `MetricInstruction.amount`, `file_history`, a test name, "use-case"; `.gitignore`'s
  `.coverage.*`.
- Block 40: `docs/contributing/amule-bump.md` cites `domain/pull_request_body.py`.
- Block 61: `code-pattern-check`'s help names the rule.
- Block 70: an absent templates directory, which read as empty.
- Block 72: coverage.py's connection left open on a data file that is no database, closed with
  `CoverageData.close(force=True)`.
- Block 80: `AGENTS.md`'s "status board" in the Naming rule, stale since block 20.

## Class 2 questions

- Block 10: Acceptance 13 asked that `test_search_tasks.py` open no SQLite connection; D4 removes only `local.db`.
  Operator: "B", the acceptance corrected to `open_local\|SavesRecorded`.
- Block 12: 1175 lines, 16 files. Operator: "1", the exemption, no split; block 14 took it beforehand for the same
  shape.

## Names settled by teammates

`canonical_native_id.py`; `seed`, `seed_whole_episode`, `seed_retracted`; `_catalog_entry_displays` and the other
`app.py` helpers, `fail_set_completed_for`, `fail_set_seen`, `_definition_token_references`;
`FileHistoryDisplay.observations`, `.sharing_periods`, `backoff_states`, `_SQL_VARIANT_LATEST_SEEN`,
`local_read_connections`, `catalog_read_connections`, `MetricInstruction.amount`; `check_release_tag`,
`tagged_commit_id`; `DOCKERFILE_PATH`, `PULL_REQUEST_BODY_FILENAME`, `timeout_seconds`, `FakeGithubServer.is_holding`;
`evaluate_claim_coverage`, `BrokenInputError`; `port_sync_enabled`; `stop_timeout_seconds`, `_GRYPE_EXECUTABLE`;
`RefusedNode`, `FilteredLoop`, `LogicConstruct`, `parse_template`, `templates_by_path`; the six coverage problem
types and `UnitCoverageProblem`, `TreeProblem`; `DEFAULT_CONFIG_PATH`, `DEFAULT_TARGETS_PATH`,
`DEFAULT_MATCHER_PATH`, `writer-verbs`, `no-literal-option-default`, `shutdown_requested` (the fake's).

## Backlog

Reconciled by the closing block: unchanged. The lot ships no entry: "A copy before a migration that rewrites rows"
stays open and comes before any release; "Contract tests for the fakes" follows lot C; "The ast-grep rule tests bound
to their rules by design" stays open (blocks 61, 80 and the closing block met it again); "Sort the files view by first
seen" keeps the `last_seen` value this lot kept. No finding exits to the backlog: the run state's exception is
written where the decision lives (`AGENTS.md`), and the logger names left untested are under "Not validated".

## For lot C and after

- **D8**: `ObservabilityDispatcher` and the `*Deps` bags keep their names; lot C's A1 to A3 reshape them (the dispatch
  a step, the bags without their `shutdown` event), and rename them once.
- **D9**: the logger `p2pwatch.observability` now has its module's name and changes again, by itself, with A3; a
  release between lots B and C shows operators both changes, an accepted cost.
- **The run state's pair holds by name only**: `RunStateReader` reads `is_paused`, not what
  `set_shutdown_requested` writes, which the loops still read through the raw `shutdown` event. A1 gives the reader
  the waits on the resume and the shutdown.
- **For "Contract tests for the fakes"**: `FakeRunStateStore` now reads back at once what the real store applies on
  the crawler's next loop tick.
- **amule's adapters and C4's adapter form**: `S6ServiceSupervisor` logs through `logging.getLogger(__name__)` (block
  94), while amule's other adapters still receive the `Logger` port from the composition, named
  `StdlibLogger(<Class>.__module__)`; a departure to weigh when lot C settles the loggers.
- **The ast-grep rule tests bound to their rules** (Backlog): `ast-grep test` silently skips a test whose rule does
  not exist, so a test written first does not fail (blocks 61, 80).

## Pitfalls

- **Serena's pyrefly does not see edits made outside it** (perl, `poe fix`'s reformatting): a later `rename_symbol`
  writes at stale offsets (`def _periThreadReadConnectionswindow`), and two of its own renames in a row can garble a
  line (`AllDef | AnyDef`). Check each batch with `git diff --word-diff`; restart Serena after outside edits (block
  20 needed two).
- **`rename_symbol` on a dataclass field** misses its constructor's keywords and the templates (blocks 20, 22); mypy
  and grep find the misses.
- **A fixture cannot be renamed by Serena** (block 14): a script over exact patterns, then `git grep -w`.
- **`ast-grep test` skips a rule test whose rule does not exist** (blocks 61, 80): `9 passed` (then `10 passed`)
  with the new test present. Watch the rule fail on the tree or on an injection, or mutate it.
- **`git add -A` sweeps coverage's parallel data files** (block 20), now ignored by `.coverage.*`.
- **A token-level script renames a file's locals safely** (closing block): Python's `tokenize` renames NAME tokens
  only, never a string or a comment, but a keyword argument too, which mypy then checks; the prose is reworded apart.
- **A test that mutates the composition must use a name it imports**: `StdlibLogger(rejudge_file.__module__)`, not
  imported there, crashed the crawl and failed on a timeout instead of on the name (closing block).
- **`git checkout <file>` to undo an injection** also discards that file's uncommitted work (block 80): inject into
  committed files only, or keep a copy.
- **`ruff check --fix` before the imports point at a new module** sorts the missing one as third-party; ruff format's
  magic trailing comma keeps an import exploded (block 16).
- **A split store adds a fixture to every step test** that passed `catalog` as several ports, and ruff reflows the
  calls (blocks 12, 14).
- **tach**: a driving port that starts importing a domain type needs its `depends_on` (blocks 54, 74).
- **The PreToolUse hook** on consecutive `grep` calls can block a whole Bash command, edits included: check
  `git status` after a blocked command (block 54).
- **`rglob`** yields nothing for an absent directory or a file and skips an unreadable subdirectory silently;
  `Path.walk(on_error=...)` reports all three (block 70).
- **poe's `uses` aborts the task graph** when the used task fails, so `dead-code-check` fails on a broken template
  (block 70).
- **The lead's scratchpad is shared**: a block's scratch files go in a subdirectory (block 22).
- **`gh stack submit`** opened two blocks' pull requests together (block 52).
- **Host port 4711 is the deployed node's**: never publish it, never touch the `mulewatch-*` containers.

## Not validated

- The integration suites locally; CI runs them on both architectures, the compose smoke's insert into
  `downloads.latest_seen_at` included.
- The amule image neither built nor run: the s6 command line checked by the unit tests only (block 62).
- The two workflows on GitHub: the Grype scan on dispatch (Acceptance 14), the release on a tag.
- The spec's "17 sites on `main`" of Acceptance 4 (block 61).
- The logger names of `SearchTaskRunner` and `record_observation`, which log only on a `StoreError` no wiring test
  can provoke; only `no-literal-logger-name` keeps them from a literal, not from a wrong class.
- Block 70's unreadable-subdirectory test is skipped when run as root.

## Wrap counts

From `gh run list --branch <branch>` over blocks 10 to 74 (2026-10-23) and the lead's count.

- **Fix-backs**: 0. **Cascaded rebases**: 0. **Runs re-triggered by them**: 0; one run per block, all green.
- **Splits**: 3 (block 52 into 52 and 53, block 60 into 60 and 61, both at the file bound; the closing block into 90,
  92 and 94 at both bounds, cut by the lead at its commits: 90 at `fb1317a9`, 92 at `6c4970ad`, 94 on top).
- **Exemptions**: 6 (blocks 12, 14, 16, 20, 22 and 90: 16, 20 and 22 on their rows, 12, 14 and 90 approved in Act;
  90 measured 596 lines, 49 files, the names and the prose).
- **Bodies called unreadable**: none known at writing.

## Next

- The lead: dispatch `grype-scan.yml` on the top branch and fill Acceptance 14; the operator reads the stack.
- After the merge: "A copy before a migration that rewrites rows" before any release; then lot C's Discuss and spec
  (A1 to A3 and the crawler's other design rows of the ledger).
