# Hexagonal architecture, lot 1: foundations

- Date: 2026-10-18. Status: approved by the operator (2026-10-18), after the spec review
  (`.reviews/hexagonal-foundations-spec.md`: 1 critical, 10 major, 22 minor, all answered).
- Tier: Spec. What an operator sees change: the commands (`python -m p2pwatch crawl`, `validate-config`, `merge`)
  and some logger names.
- Origin: lot 1 of the umbrella spec `agents/specs/2026-10-18-hexagonal-architecture.md`, whose decisions this one
  applies without restating them. Section "Corrections of the umbrella" lists where it departs from it.
- Paths are under `packages/crawler/src/p2pwatch/` unless noted. The measurements are in the appendix.

## Summary

- **The composition only builds and connects objects.** The logic it holds today moves to units with their own
  tests. The test factories go, and tests that run the real assembly against a fake amuleapi replace them.
- **The command line becomes an adapter** that calls three ports: one to crawl, one to validate the config, one to
  merge catalogs.
- **Every package moves to the ring layout** (`domain`, `ports`, `application`, `adapters`, `composition`), and
  every package is run through explicit subcommands.
- **A tool checks the rings**: tach for the imports between rings, ast-grep for what the core may import.

## Two lots

The work is two lots, each with its own stack and holistic review: **lot 1a** (the composition and the command
line, 10 blocks) and **lot 1b** (the moves, the entry points and the check, 9 blocks). One stack of 19 pull
requests would be too long to review in one sitting.

## Lot 1a: the composition and the command line

### The composition's logic moves out

`composition/app.py` mixes wiring with logic that only its factory-driven tests check. Each piece moves to a unit
tested on its own:

| Logic | New home |
|---|---|
| signals, the second signal forcing the exit, the final best-effort close | `PosixProcess`, an adapter in `adapters/driving/process/` |
| running the loops until the stop, then cancelling them all | `supervise_loops`, in `application/` |
| the webui's thread: start, failure, stop | `UvicornServerThread`, in the webui's HTTP adapter |
| tolerating an unreachable amuled at startup | `AmuleApiClient.open()` |
| metrics server on or off | the Prometheus adapter |
| values derived from the config (intervals, defaults, policy fingerprint) | the config adapter |
| the configured `node_id` overriding the stored one | `resolve_node_id`, in `application/` |
| the re-evaluation's two log lines | `reevaluate_if_policy_changed` |
| logging setup and level | the command-line adapter |

Two `if` stay in the composition, download on or off and webui on or off: they choose what to wire.

Each block that moves a piece also deletes the test seam it replaces, so no seam outlives its last use.

### How the crawler stops

1. A signal reaches `PosixProcess`; a click on "restart" reaches the webui.
2. Both call `CrawlerControl.request_shutdown()`, today's `restart()` renamed, since a SIGTERM does not mean
   "restart". The webui's route and button do not change.
3. `supervise_loops` sees the stop, arms the shutdown deadline, then cancels the loops.
4. The composition closes its resources under that deadline; `PosixProcess` closes whatever is left.

The deadline is armed where the stop is seen, so a stop from the webui is bounded too.

### No more factories

The client factories, the webui server factory, the metrics seam and the types that only exist to type them
(`MuleClient`, `DownloadSourceClient`, `WebuiServer`) are deleted, with `tests/composition/test_app.py`.

The composition takes two plain values instead: the webui address and the amuleapi address. Production passes
`0.0.0.0:8080` and `ed2k:4711`; a test passes `127.0.0.1:0` and its fake.

The two amuleapi sessions (search and status share one, downloads have their own) stay as they are; lot 2
changes them.

### A webui that fails to bind says so

Today, when port 8080 is taken, uvicorn exits its thread and p2pwatch logs nothing. `UvicornServerThread` waits
for uvicorn to report that it started. If it does not, it logs "webui degraded" with the error, and the crawler
carries on.

### The wiring tests

They run in the gate, against `FakeAmuleApiServer`, today's amuleapi fake served on a local socket. Each one is a
fact about the assembly that no unit test can see:

1. **Full mode**: the crawler logs in, catalogues a result with the configured `node_id`, queues a download,
   serves the webui on the address it was given, and stops when the restart button is pressed.
2. **Observer mode with two ed2k keywords**: only one search starts before a SIGTERM stops it. Two would mean each
   search has its own client, which would break the network's pacing.
3. **`crawl` with a broken config** exits 1.
4. **`validate-config`** exits 0 on the shipped config, 1 on a broken one.
5. **`merge`** of two catalogs into a new file holds both, and exits 0.

Tests 1 and 2 live in `tests/composition/test_app_wiring.py`, tests 3 to 5 in `tests/test_main.py`. With those
names, `coverage_checks` already counts them as the composition's own tests, so it needs no change.

### The command line

The command line becomes an adapter, `adapters/driving/cli/`. It parses the arguments, picks the subcommand, sets
up logging and turns errors into exit codes (unchanged: 1 for a bad config, 2 for a refused merge). It calls three
ports:

| Port | Implemented by | Over |
|---|---|---|
| `CrawlerRunner.crawl(...)` | the composition | |
| `ConfigValidator.validate_config(...)` | the use case `ValidateConfig` | `ConfigChecker`, implemented by the config adapter |
| `CatalogMerger.merge_catalogs(...)` | the use case `MergeCatalogs` | `CatalogFinder` (does this catalog exist?) and `CatalogCopier` (copy the rows) |

- **`crawl` is implemented by the composition**, because what it builds depends on the config the command line
  just read. It is the only port not implemented by a use case.
- **`merge`'s safety rules move into `MergeCatalogs`**: the sources must exist, a new output must not, `--into`
  must name one of the sources. They are the tool's "no accidental loss" policy, not argument syntax.
- **An invalid config is one error type in the domain**, `InvalidConfigError`. The command line may not import an
  adapter's errors, and the composition has no `try` to translate them.
- **The ports take paths as `PurePath`**, which does no I/O.
- The root `p2pwatch/__main__.py` builds the three implementations and hands them to the command line.

`python -m p2pwatch --config ...` (without `crawl`) and `python -m p2pwatch.merge` stop working. Both are v5
breaks, written in `docs/migration-4x.md`; the Dockerfile and the docs follow.

### Names

- **A port is named after the one who does its action**: `CatalogMerger`, "the one who merges catalogs".
  Existing ports that break the rule (`CrawlerControl`, `StatusReadings`, `DiskSpace`, `Telemetry`, `Rng`,
  `WakeHub`) are renamed by lot 2, which rewrites them all.
- **A use case is named after its operation**: `ValidateConfig`, `MergeCatalogs`.
- **An adapter is named by its technology and what it adapts**: `PosixProcess`, `UvicornServerThread`,
  `YamlConfigChecker`, `PathlibCatalogFinder`, `SqliteCatalogCopier`.
- **A test double is `Fake` and what it replaces**: `FakeAmuleApiServer`; `FakeMuleClient` becomes
  `FakeAmuleApiClient`.
- **The new ports are ABCs**, so lot 2 has nothing to convert.

`AGENTS.md` gains these rules and the words `ring`, `hexagon`, `driving`, `driven` and `use case`.

### Blocks

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `test/amuleapi-loopback-fake` | this spec, the umbrella's corrections, the backlog's lot 1 split in two; `FakeAmuleApiServer` | 150, 6 |
| 20 | `refactor/webui-server-thread` | `UvicornServerThread`, the webui address parameter, the webui factory deleted | 380, 8 |
| 30 | `test/composition-wiring` | the amuleapi address parameter, wiring tests 1 and 2 | 380, 8 |
| 40 | `refactor/process-and-loops` | `PosixProcess`, `supervise_loops`, `request_shutdown` | 500, 14 |
| 50 | `refactor/composition-derived-values` | the other moves of the table, `InvalidConfigError`, the metrics seam deleted | 450, 18 |
| 60 | `refactor/composition-only-wires` | the client factories and `test_app.py` deleted | 1,400, 10 |
| 70 | `feat/validate-config-use-case` | `ValidateConfig` and its ports, called by today's command line | 280, 10 |
| 80 | `feat/cli-subcommands` | the command-line adapter, `crawl` and `validate-config`, wiring tests 3 and 4, the Dockerfile, the docs | 480, 17 |
| 90 | `feat/merge-use-case` | `MergeCatalogs` and its ports, the `merge` subcommand, `merge/` deleted, wiring test 5 | 480, 18 |
| 100 | `docs/hexagonal-composition-wrap` | closing block: backlog, handoff | |

- Block 60 passes 500 lines because it deletes the rest of `test_app.py`, about 1,300 lines; a deletion reads at
  a glance.
- Block 80 passes 500 lines because it deletes the old entry point and its 300-line test file; a deletion reads
  at a glance. (Corrected 2026-10-18: measured at 859 lines, 439 of them the two deleted files.)
- In blocks 20 to 50, the wiring tests and what is left of `test_app.py` live side by side.
- In block 50, the client types gain `open()` for one block, until block 60 deletes them.

## Lot 1b: the rings, the entry points and the check

Lot 1b starts once lot 1a has merged.

### Where each module goes

The rule: **a module goes where it will stay once lots 2 and 3 are done**, so that no file moves twice. Two
constraints:

- a module that does I/O (`os`, `subprocess`, `sqlite3`, file access) goes to an adapter, even if most of it is
  logic; lot 3 pulls the logic out;
- the core never imports an adapter: tach refuses it outright, so where the placement would create such an import,
  the imported piece moves into the core now.

Everything else that breaks a ring rule for now is declared in `tach.toml` as a temporary exception, with the lot
that removes it.

| Today | Goes to | Temporary exception, removed by |
|---|---|---|
| `ports/*.py` | `ports/driven/`; `crawler_control.py` to `ports/driving/` | the webui imports driven ports: lot 2 |
| `adapters/**` | `adapters/driven/` | |
| `webui/` (pages, views, templates) | `adapters/driving/webui/` | the readers import the views: lot 2 |
| the webui's three SQLite readers | `adapters/driven/persistence_sqlite/` | |
| `webui/adapters/matching_read.py` | `application/` | the webui imports it directly: lot 2 |
| `catalog_matching/*` | `catalog_matching/domain/` | |
| `p2pwatch_amule` | `boot/conf.py` to `domain/`, the rest to `adapters/` | adapters importing adapters: lot 3 |
| `vex_checks` | descriptors, registry and violations to `domain/`, the rest to `adapters/` | about 10: lot 3 |
| `template_checks` | `adapters/driving/` | |
| `coverage_checks` | `function_bodies` to `domain/`, the rest to `adapters/` | one: lot 3 |
| `amule_bump` | `dockerfile`, `body` and `BumpError` to `domain/`, `release` to `application/`; `github.py` split into a port, a constant in the domain and an HTTP adapter | lot 3 |
| `p2pwatch_testing` | unchanged, only its imports are updated | |

The webui's shared test fixtures move to `p2pwatch_testing`, and each moved test module asks for them explicitly,
so they wrap exactly the tests they wrap today.

### Every package is run through a subcommand

| Package | Subcommands |
|---|---|
| `p2pwatch` | `crawl`, `validate-config`, `merge` (lot 1a) |
| `p2pwatch_amule` | `boot`, `port-sync` |
| `vex_checks` | `image-claims`, `stale-claims`, `source-claims`, `claim-coverage` |
| `template_checks` | `logic-free`, `read-names` |
| `coverage_checks` | `unit-coverage` |
| `amule_bump` | `bump` |

Each package parses its commands in its own `adapters/driving/cli.py`, and its root `__main__.py` only hands over
to it. The Docker entrypoint, the s6 script, the workflows and the poe tasks follow.

### The check

- **tach** (0.35.3), run in the gate as `architecture-check`, checks that imports point inward, that adapters do
  not import each other, that the six hexagons stay apart, and that no module escapes its declaration.
- **ast-grep** checks that the core imports only from a short list per ring (the pure standard library it uses
  today, a few `asyncio` and `uuid` names, `PurePath`). `logging` stays allowed in `application/` until lot 2.
- The ban on `Protocol` waits for lots 2 and 3, which remove the last ones.

### Strings no tool sees

Each move block rewrites by hand, and lists in its pull request: logger names, package names inside strings,
template paths, test-config keys, `parents[N]` paths, `prog=` strings, the Dockerfile, the entrypoint and s6
scripts, the workflows' commands, and module paths in `docs/`.

Logger names follow their module, so an operator filtering logs on a module's name sees it change. Lot 2 replaces
them anyway.

### Blocks

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `refactor/matching-domain-ring` | `catalog_matching` into `domain/` | 115, 65 |
| 20 | `refactor/crawler-ports-adapters-rings` | the crawler's ports and adapters | 450, 180 |
| 30 | `refactor/webui-rings` | the webui, its fixtures, its template paths | 300, 45 |
| 40 | `refactor/amule-rings` | `p2pwatch_amule` | 60, 15 |
| 50 | `feat/amule-entry-points` | its subcommands, the entrypoint and s6 scripts | 250, 10 |
| 60 | `refactor/tooling-rings` | the four tooling packages, `github.py` split | 200, 45 |
| 70 | `feat/tooling-entry-points` | their subcommands, the workflows, poe | 450, 19 |
| 80 | `feat/architecture-gate` | tach, ast-grep, `AGENTS.md`'s architecture rules | 450, 15 |
| 90 | `docs/hexagonal-rings-wrap` | closing block: backlog, handoff | |

- Blocks 10 to 40 and 60 pass 20 files: they are mechanical moves (`git mv` plus an import rewrite), which take the
  size exemption.
- Each package's moves come before its subcommands, so the new command-line adapter is born in its ring.

## Acceptance

1. **No factory is left** (lot 1a, block 60): `git grep -nE 'client_factory|webui_server_factory|\bmetrics_server\b|\bMuleClient\b|FakeMuleClient|DownloadSourceClient|\bWebuiServer\b' -- packages/` prints nothing. (Corrected 2026-10-18: `metrics_server` takes `\b`, since block 50's `start_metrics_server` is not the seam.) On `main` it prints the composition, `ports/mule_client.py`, the client's docstring, the fakes and the tests.
2. **The composition holds no logic** (lot 1a, block 60): `CrawlerApp` has no `try`, no `except`, no
   `suppress`, no conditional expression, no `and`/`or`, and no `if` but the two kept. On `main` it has four `try`
   and six `if`.
3. **Each wiring test catches a broken assembly**: each is seen failing against a deliberate break, its failure
   quoted in the pull request. Test 1: the webui address ignored. Test 2: one client per search. Test 3: the
   config error swallowed. Test 4: the matcher file skipped. Test 5: only the first catalog copied.
4. **A failed bind is reported**: a test holds a port, starts the webui on it, and sees "webui degraded" without
   an exception. On `main`, nothing is logged.
5. **A stop from the webui is bounded**: a test of `supervise_loops` stops it without a signal and sees the
   deadline armed before the loops are cancelled.
6. **The commands**: `python -m p2pwatch --config deploy/crawler.yml` exits 2 with a usage line,
   `python -m p2pwatch.merge` finds no module, `python -m p2pwatch validate-config` prints "Config valid" (with
   `AMULE_API_PASSWORD` set), and every package's `--help` lists its subcommands.
7. **The check refuses what it should** (lot 1b, block 80): `architecture-check` passes, then fails on a domain
   module importing `application/`, on an adapter importing another adapter, on `p2pwatch_amule` importing
   `p2pwatch`, and on an undeclared new module. ast-grep fails on `import sqlite3` in the domain and passes on
   `import dataclasses`.
8. **The gate is green** at every block, and CI's smoke and integration suites pass on amd64 and arm64 at the
   blocks that change what the images run (lot 1a: 60, 80, 90; lot 1b: 20, 50, 70).
9. **Nothing out of scope changes**: no migration's content, no deployment file, no webui route.
   `git diff -M100% --name-status origin/main...<top branch> -- '*/migrations/*' deploy/crawler.yml deploy/compose.yml deploy/ed2k | grep -v '^R100'` prints nothing.

## Risks

- **Logger names change** with their modules.
- **The wiring tests run in real time**, a few seconds each; they stop on what the fake sees, never on a sleep.
- **The temporary exceptions are debt on purpose**: tach fails as soon as one is no longer used, and still refuses
  any new one.

## Backlog

- **Hexagonal architecture**: the "Lot 1" item becomes two, 1a and 1b, each deleted when its lot ships. Lot 2
  loses `merge`, done here.
- **A copy before a migration that rewrites rows** stays open, and must ship before the next release. Lots 1a and
  1b change both images, so neither is released before it.
- Every other item stays open: none concerns the rings, and the webui ones are better after lot 2.

## Corrections of the umbrella

Marked `(Corrected 2026-10-18: ...)` in the umbrella by lot 1a's block 10:

- One port, `CrawlerRunner`, is implemented by the composition.
- The test seams are more than three, and the orchestration integration test uses one too; the composition's logic
  moves out; `coverage_checks` needs no change.
- The loopback fake is about 45 lines, and it is the webui adapter, not the composition, that watches uvicorn's
  start.
- Four packages gain a root `__main__.py`, `coverage_checks` has a single entry point, and `py.typed` stays at the
  root.
- A module that does I/O goes to an adapter, and the core never imports an adapter.
- `merge` moves to a use case in lot 1 instead of lot 2, and lot 1 becomes lots 1a and 1b.

## Appendix: measurements

Taken on `main` at `07f57c1` on 2026-10-18 and recounted by the spec review. Re-run before acting on one.

- `composition/app.py`: 581 lines; `grep -nE '^\s+(if|elif|try:)'` prints four `try` and six `if`, beside two
  conditional expressions and the `node_id` `or`.
- Test seams: `client_factory`, `download_client_factory`, `webui_server_factory`, `metrics_server` (whose
  default is `# pragma: no cover`), three `monkeypatch.setattr` targets, and the private `_on_signal`,
  `_shutdown` and `_resumed` (12 and 13 uses in `test_app.py`). `tests/integration/test_crawler_loop.py` uses
  `client_factory`.
- `test_app.py`: 1,578 lines, 39 tests. `test_main.py`: 19 tests, 16 on the command line, 3 on
  `build_crawler_app`.
- The silent failed bind, reproduced with uvicorn 0.54.0: uvicorn logs `[Errno 98]` on its own logger and calls
  `sys.exit(3)`; `_serve_webui` catches `Exception` only, after "webui serving" was logged before the bind.
- `Server.started` turns true after the bind, and `server.servers[0].sockets[0].getsockname()` gives the port
  bound for port 0.
- The loopback fake: about 45 lines; uvicorn needs `interface="asgi3"` and `lifespan="off"`.
- `coverage_checks` maps a test file to the longest module name it extends with `_`, so
  `test_app_wiring.py` belongs to `app.py`.
- The moves: 97 modules and 35 data files, 7 `__init__.py` deleted, 111 test files moved, about 540 import
  statements in about 185 files rewritten.
- tach 0.35.3 (MIT, `tach-org/tach`): one configuration accepts all the options used; a temporary exception
  between adapters only warns, but a core module importing an adapter fails even when declared temporary.
- Under the placement above, before `amule_bump`'s split, three core modules would import an adapter: `body`,
  `release` and `dockerfile`.

## Appendix: notes for the teammates

Details the body leaves out, each settled during the Discuss or the review.

- **The shutdown deadline** is an `asyncio.timeout(None)` the composition opens around the loops and the close.
  `supervise_loops` receives a callback, `arm_shutdown_bound`, which the composition writes to reschedule it to the
  event loop's time plus `shutdown_deadline_seconds`, so `application/` never reads that time. A fired deadline
  still escapes as a bare `TimeoutError` (the command line exits 0, as today), because `PosixProcess`'s final
  close suppresses its own failures; a worker's exception still escapes as an `ExceptionGroup`.
- **`PosixProcess`** is an async context manager: it installs the SIGINT and SIGTERM handlers on entry, and on exit
  closes the resources it holds with `suppress(BaseException)`, then removes the handlers. It prints the two
  signal lines; the three straight-line progress lines of the stop stay in the composition.
- **`UvicornServerThread.start()`** waits, with a bound, for uvicorn's `started` or the thread's end; the thread
  body catches `SystemExit` beside `Exception`. "webui serving on" is logged after the bind, with the host and
  port really bound.
- **Wiring test 1** asserts the bound host is the one given and the port is not 8080 when 0 was given. **Wiring
  test 2** asserts SIGTERM's handler is installed before sending it, so a broken handler fails an assertion
  instead of killing the test process.
- **The orchestration integration test** passes the caller's daemon as the amuleapi address and stops on a
  SIGTERM, in block 60.
- **`CatalogMerger.merge_catalogs(source_catalogs, destination)`** takes a destination type the port owns:
  `NewCatalog(path, force)` or `ListedSourceCatalog(path)`. `CatalogFinder.find_catalog(path)` returns the
  resolved path, or `None` when there is no catalog. `CatalogCopier.copy_catalogs` keeps today's
  `destination_is_source` flag. The command line keeps one rule, no `--force` with `--into`. `MergeCatalogs` maps
  the copier's errors into the merger's.
- **`InvalidConfigError`** lives in `domain/invalid_config.py`; the config adapter raises it for a YAML that does
  not load, a key that does not parse, and a wrapped `MatchingConfigError`.
- **Logging**: the command-line adapter calls `basicConfig` for every subcommand; `crawl` then sets the root level
  from the config.
- **`test_main.py`'s command-line tests** move to the command-line adapter's tests, but
  `test_bare_invocation_still_runs_the_crawler`, which is inverted.
- **The webui's fixtures** move to `p2pwatch_testing`, registered once by `pytest_plugins` in the crawler's
  top-level `tests/conftest.py`; the `sqlite3.connect` patch stops being autouse, and each moved test module it
  wrapped requests it with `pytestmark = pytest.mark.usefixtures(...)`. The three destinations:
  `tests/adapters/driven/persistence_sqlite/`, `tests/adapters/driving/webui/`, `tests/application/`.
- **tach**: one module per port file and per adapter; the source roots exclude `packages/crawler_testing/src`;
  the root `__main__.py` modules are in the composition layer; every temporary exception is a dependency declared
  `deprecated = true` with a comment naming the lot that removes it, never a `# tach-ignore`.
- **ast-grep's lists**, per core ring, from the imports the ring holds after the moves: `asyncio` by name
  (`Event`, `TaskGroup`, `wait`, `FIRST_COMPLETED`, `ensure_future`, `CancelledError`, `sleep`), `uuid` by name
  (`uuid5`, `NAMESPACE_URL`), `pathlib` by `PurePath`, plus `configparser` and `io` for `p2pwatch_amule`,
  `difflib` and `textwrap` for `amule_bump`, `ast` for `coverage_checks`.
- **The strings to rewrite by hand**, beyond the logger names: the `importlib.resources` package strings (6
  files), the monkeypatch dotted targets (5), the template paths anchored on `p2pwatch.webui`, the 17
  `tests_without_unit` keys, `vex_checks/repo.py`'s `parents[4]`, the comment of `deploy/matcher.yml:59`.
- **`catalog_matching`'s `tests/fixtures/` and `test_golden_corpus.py`** stay where they are.
