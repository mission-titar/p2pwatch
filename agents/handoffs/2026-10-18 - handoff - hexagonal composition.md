# Handoff: hexagonal composition, lot 1a of the hexagonal architecture umbrella

Drafted by block 95 from the lot's block reports (#252 to #261, and blocks 90 and 95), for the closing block 100
to correct: the holistic review's findings and their exits, `BACKLOG.md`, the Wrap counts.

## State

Tier Spec lot. Spec `agents/specs/2026-10-18-hexagonal-foundations.md`, approved by the operator on 2026-10-18
after its review (`.reviews/hexagonal-foundations-spec.md`, gitignored: 1 critical, 10 major, 22 minor, all
answered). The lot carries out the first half of lot 1 of the umbrella spec
`agents/specs/2026-10-18-hexagonal-architecture.md`, which block 10 corrected where lot 1 departs from it.

Twelve blocks, one stack cut from `main` at `07f57c1`:

| Block | Pull request | Branch |
|---|---|---|
| 10 | #252 | `test/amuleapi-loopback-fake` |
| 20 | #253 | `refactor/webui-server-thread` |
| 30 | #255 | `test/composition-wiring` |
| 40 | #256 | `refactor/process-and-loops` |
| 50 | #257 | `refactor/composition-derived-values` |
| 55 | #258 | `refactor/startup-open-and-node-id` |
| 60 | #259 | `refactor/composition-only-wires` |
| 70 | #260 | `feat/validate-config-use-case` |
| 80 | #261 | `feat/cli-subcommands` |
| 90 | opened with this handoff's block | `feat/merge-use-case` |
| 95 | opened with this handoff | `feat/cli-merge` |
| 100 | the closing block | `docs/hexagonal-composition-wrap` |

Nothing of the stack is merged. The lot changes what the core image runs (its `CMD`, its commands, some log
lines), so Wrap (f) proposes a release, but not before the backlog's "A copy before a migration that rewrites
rows" ships (spec, section "Backlog").

## What was built

- **`FakeAmuleApiServer`** (block 10): today's `FakeAmuleApi` served by uvicorn on `127.0.0.1:0` from its own
  thread. It binds its socket itself before uvicorn starts, so its port is known at once, and it raises its first
  refused request again when its block exits. Block 30 gave it `wait_for(predicate, timeout_seconds)`.
- **`UvicornServerThread`** (block 20, `webui/composition/uvicorn_server_thread.py`): `start()` waits up to 5 s
  for uvicorn's bind or the thread's end. A failed bind logs "webui degraded: the crawler carries on without
  HTTP" with the traceback, and the crawler carries on (acceptance 4). "webui serving on" names the address
  really bound. `CrawlerApp` takes `webui_address`; the webui server factory is deleted.
- **The amuleapi address as a plain value** (block 30): `CrawlerApp` takes `amule_api_address`. Wiring tests 1
  (full mode) and 2 (observer mode, two ed2k keywords, a real SIGTERM) run the real assembly against the
  loopback fake, in `tests/composition/test_app_wiring.py`.
- **`PosixProcess` and `supervise_loops`** (block 40): the signals, the second signal's forced exit and the final
  best-effort close move to `adapters/driving/process/posix_process.py`; the loops' supervision and the shutdown
  deadline armed where the stop is seen move to `application/supervise_loops.py` (acceptance 5).
  `CrawlerControl.restart()` becomes `request_shutdown()`; the webui's route and button stay `/controls/restart`.
- **The config's derived values and the metrics server** (block 50): `load_config` loads the three files and the
  policy fingerprint, and raises the domain's `InvalidConfigError` for every refusal. The config dataclasses
  carry the observability defaults, the metrics port, the time between source reads and `lost_after`.
  `start_metrics_server` returns the server's stop, so the metrics server now stops at shutdown. The
  `metrics_server` seam is deleted.
- **`AmuleApiClient.open()`, `resolve_node_id`, the re-evaluation's log lines** (block 55): an amuled not
  listening at startup is tolerated by the client, the configured `node_id` overriding the stored one is a use
  case, and `reevaluate_if_policy_changed` logs its own outcome.
- **No more factories** (block 60): the two client factories, `MuleClient`, `DownloadSourceClient`,
  `AmuleEndpoint` and `tests/composition/test_app.py` (28 tests) are deleted. `CrawlerApp` builds both amuleapi
  sessions in place. Two new wiring tests: the shutdown deadline cuts a logout the fake stalls, and a saved
  backoff holds the first search. `FakeMuleClient` becomes `FakeAmuleApiClient`. Acceptances 1 and 2 hold: no
  factory is left, and `CrawlerApp`'s only `if`s are the webui and download choices.
- **`ValidateConfig`** (block 70): the driving port `ConfigValidator` and the driven port `ConfigChecker`, the
  latter implemented by `YamlConfigChecker`. Both ports are ABCs, born in `ports/driving/` and `ports/driven/`.
- **The command line, an adapter** (block 80): `ArgparseCommandLine` in `adapters/driving/cli/`. The driving port
  `CrawlerRunner` is implemented by `CrawlerAssembly`, a composition class beside `CrawlerApp`. The root
  `p2pwatch/__main__.py` holds `0.0.0.0:8080`, `ed2k:4711` and `os.environ`. `python -m p2pwatch crawl` is
  required, and the image's `CMD` runs it. Wiring tests 3 and 4 are in `tests/test_main.py`.
- **`MergeCatalogs`** (block 90): the driving port `CatalogMerger`, which owns `NewCatalog(path, force)`,
  `ListedSourceCatalog(path)` and `MergeError`. Two driven ports: `CatalogFinder`, implemented by
  `PathlibCatalogFinder` (`adapters/pathlib_catalog_finder.py`), and `CatalogCopier`, which owns
  `CatalogCopyError` and is implemented by `SqliteCatalogCopier`, the former `merge/merger.py` moved with
  `git mv`. The safety rules (the sources exist, a new catalog does not unless forced, `--into` names a source)
  are the use case's. The command line keeps one rule: no `--force` with `--into`.
- **The `merge` subcommand** (block 95): `python -m p2pwatch merge` over `CatalogMerger`, and `p2pwatch.merge`
  deleted. Wiring test 5 merges two catalogs into a new one through the root `__main__`.

## What an operator sees change

- **v5 breaks**, written in `docs/migration-4x.md`:
  - `python -m p2pwatch` without a subcommand exits 2 with a usage line, and the image's `CMD` runs `crawl`;
  - `python -m p2pwatch.merge` is gone: the merge is `python -m p2pwatch merge`, with the same options.
- **Two merge refusals are reworded** (block 90), so that the use case does not name the command line's flags:
  - `--into must name a listed source catalog: X` becomes `destination must be one of the source catalogs: X`;
  - `output already exists: X (use --force to merge into it)` becomes
    `destination already exists: X (force the merge to append to it)`.
- **Messages:**
  - "webui thread crashed" becomes "webui degraded: the crawler carries on without HTTP" (block 20);
  - the two startup warnings for an unreachable amuled become one line per session (block 55):
    `amuled unreachable at startup (POST /auth/login: connection refused): tolerated, the loops retry`.
- **Logger names:**
  - "webui serving on": `p2pwatch.webui.composition.uvicorn_server_thread` (block 20);
  - the signal lines: `p2pwatch.adapters.driving.process.posix_process` (block 40);
  - the startup tolerance: `p2pwatch.adapters.mule_api.client`; the re-evaluation lines:
    `p2pwatch.application.reevaluate_if_policy_changed` (block 55);
  - the merge's lines: `p2pwatch.application.merge_catalogs` (was `p2pwatch.merge`) and
    `p2pwatch.adapters.persistence_sqlite.sqlite_catalog_copier` (was `p2pwatch.merge.merger`) (block 90).
- **The metrics server is closed at shutdown** with the other resources (block 50). Its `shutdown()` waits up to
  0.5 s, within the shutdown deadline.

## Acceptance

1. Block 60: the `git grep` prints nothing (exit 1).
2. Block 60: an `ast` walk of `CrawlerApp` finds `If` at lines 253 (webui) and 306 (download) only, and no `Try`,
   `IfExp`, `BoolOp` or `suppress`.
3. Each wiring test was seen failing against its break:
   - test 1, the webui address ignored (block 30): no "webui serving on" line, `assert 0 == 1`;
   - test 2, one client per search (block 30): `assert 2 == 1`, 5 runs out of 5;
   - test 3, the config error swallowed (block 80): `assert 0 == 1`;
   - test 4, the matcher file skipped (block 80): `assert 0 == 1`;
   - test 5, only the first catalog copied (block 95): `assert 1 == 2`.
4. Block 20: the thread body catching `Exception` only fails with `assert [] == ['webui degra...without HTTP']`.
5. Block 40: the bound armed after the unwind fails with `assert 'search cancelled' == 'armed'`.
6. The commands:
   - `python -m p2pwatch --config deploy/crawler.yml` prints the usage line and `invalid choice`, exit 2;
   - `AMULE_API_PASSWORD=x python -m p2pwatch validate-config` prints `Config valid`, exit 0;
   - `python -m p2pwatch.merge` prints `No module named p2pwatch.merge`, exit 1;
   - `python -m p2pwatch --help` lists `{crawl,validate-config,merge}`.

   Checked at blocks 80 and 95. The other packages' subcommands are lot 1b's.
7. Lot 1b's.
8. The gate is green at every block's tip; each run below was green.
   - CI ran its builds on amd64 and arm64 (`build-and-verify`) at blocks 60 (run `39150755593`) and 80 (run
     `39152064074`).
   - The orchestration integration suite passed locally at blocks 30 to 60 against
     `ghcr.io/mission-titar/p2pwatch-amule:main` on port 4719, since port 4711 was taken on that host.
   - Blocks 90 and 95: their pull requests' runs.
9. Blocks 80 and 95: the `git diff -M100%` command prints nothing.

## Departures from the spec

- **Two blocks were split** to stay under the size bounds, each half with its own pull request:
  - block 50 measured 770 lines and 21 files, and became 50 (474, 10) and 55 (295, 13);
  - block 90 measured 931 lines and 22 files, and became 90 (467, 12) and 95 (445, 12, of which 271 are
    deletions). Block 90's copier calls a module function from its one method, so the moved body is not
    reindented.
- **Two blocks took the size exemption**, each stated under the spec's block table:
  - block 60: 1,552 lines, 1,441 of them deletions;
  - block 80: 859 lines, 439 of them the two deleted files, marked `(Corrected 2026-10-18: ...)`.
- **`CrawlerRunner` is implemented by `CrawlerAssembly`**, not by `CrawlerApp` (block 80), since `CrawlerApp`
  takes the config already loaded. The root log level is set by `CrawlerAssembly`, not by the command line,
  which never sees the config.
- **`UvicornServerThread` lives in `webui/composition/`** beside the Starlette app (block 20); lot 1b moves it with
  the webui. Its `start()` is a coroutine that waits through `asyncio.to_thread`.
- **New ports were born in `ports/driving/` and `ports/driven/`** (blocks 70, 80, 90), and `PosixProcess` in
  `adapters/driving/process/` (block 40), where lot 1b moves the rest, so none moves twice.
- **`load_config` wraps the three error kinds into `InvalidConfigError`** at its boundary (block 50), rather than
  making the adapter's errors subclasses.
- **`SchemaVersionMismatchError` is gone** (block 90): the copier raises `CatalogCopyError` for every failure,
  and its tests match the message.
- **`merge/errors.py` is deleted in block 90**, not 95, since `MergeError` became the port's and the file would
  have been dead code.

## Spec corrections

- Acceptance 1's pattern takes `\bmetrics_server\b`, since block 50's `start_metrics_server` is not the seam
  (block 60, at the lead's request).
- Block 80's size: "measured at 859 lines, 439 of them the two deleted files" (block 80, `4aa1008`).

## Tests pruned or moved

- Blocks 20 and 30: the webui crash and default factory tests, the address and restart tests (covered by wiring
  test 1), and the endpoint constants test.
- Block 50: the three `test_metrics_server_*` and the status loop's endpoint name test.
- Block 55: the two unreachable-at-startup tests and their fakes.
- Block 60: all 28 of `test_app.py` and `tests/ports/test_mule_client.py`. The operator chose option (c),
  stated under "Class 2 questions" below. The checks lost with them are listed in #259's report: among them
  the steady-state disarmed bound, the shared pause gate, the webui wired to the status board, the clocks the
  app stamps and paces with, and an hour of the whole app keeping to the networks' rules.
- Block 80: `test_main.py`'s command-line tests move to `test_argparse_command_line.py` against fake ports;
  `test_bare_invocation_still_runs_the_crawler` is inverted; the three `build_crawler_app` tests go. The
  production `ed2k:4711` is checked only by the compose smoke.
- Block 95: `tests/merge/test_main.py` goes. Its refusals and logs are `MergeCatalogs`'s tests, its arguments
  the command line's, and its merge wiring test 5.

## Class 1 fixes

- Block 20: the `CrawlerControl` port's docstring named the deleted `_serve_webui`.
- Block 40: `vulture_whitelist.py` pointed `should_exit` at `composition/app.py`.
- Block 60: `AmuleApiClient`'s docstring named the deleted `MuleClient`.
- Block 80: `policy_fingerprint`'s docstring named `composition/__main__.py` as its caller, and lost its em-dash.
- Blocks 10, 30, 50, 55, 70, 90, 95: none.

## Class 2 questions

- Block 60: deleting `test_app.py` dropped assembly checks no other test made. Options: (a) delete them and list
  them, (b) add assertions to wiring tests 1 and 2, (c) (b) plus the deadline and backoff wiring tests.
  Operator's answer: "c".
- Blocks 90 and 95: none. The size overrun went to the lead, who chose the split.

## Pitfalls

- **uvicorn:**
  - its default `log_config` reconfigures the test process's logging, hence `log_config=None`;
  - it needs `interface="asgi3"` for a bound method and `lifespan="off"`;
  - it installs signal handlers on the main thread only, so the fake never intercepts wiring test 2's SIGTERM;
  - asyncio rewrites the bind error in lower case (`[errno 98] address already in use`);
  - the `OSError` reaches the log only as the `__context__` of uvicorn's `SystemExit`.
- **A route the fake stalls blocks uvicorn's whole loop** in the fake's thread, so a stall only fits the end of a
  run. `wait_for` holds the fake's lock while it handles a request, so a predicate always reads a settled fake.
- **A second signal's `SystemExit` escapes the event loop itself**, so its test runs the coroutine under
  `asyncio.run` inside `pytest.raises`. vulture flags `*exc_info` on `__aexit__`; `*_exc_info` passes.
- **Under pytest, `logging.basicConfig` is a no-op**, since the root already has pytest's handlers: its test
  empties `root.handlers` with `monkeypatch`. `caplog.at_level` restores the root level on exit. pytest leaves
  the root at WARNING, so an integration test's handler sets its logger to INFO.
- **`start_http_server` binds the port itself**, so the tests take a free port from a probe socket. Its
  `shutdown()` costs up to 0.5 s per test with a real metrics server.
- **Adding a method to a structural port reaches files no grep for its name finds**: a structural stub in the
  port's tests, an integration test's wrapper. mypy names both (block 55).
- **An abstract method whose body is its docstring alone is covered at import** under `branch=true`; a two-line
  `...` body is not (block 70).
- **The size measure per file loses rename pairs**: `git diff -U0 <parent>...HEAD -- <one path>` counts a moved
  file whole. Pass both paths, or measure the block as a whole (block 90).
- **Port 4711 may be taken on the host** by another container; the integration runs used a throwaway daemon on
  4719.

## Not validated

- In the container, nothing CI's compose smoke does not cover:
  - a failed webui bind (the smoke covers the bind that succeeds);
  - a real SIGTERM through `docker stop`;
  - the metrics server (the smoke does not scrape `/metrics`);
  - a cold start where amuled comes up after the core;
  - `python -m p2pwatch merge` (the smoke runs no merge).
- The orchestration integration test's new SIGTERM stop, seen failing against a break: a missed trigger costs its
  150 s wait.
- The observer wiring test's trigger is ordering in theory, not a guarantee: a second ed2k start sent at the same
  time as the first would arrive well before it.

## Holistic review

To run at the head of Wrap, over `git diff origin/main...origin/feat/cli-merge`. Its findings and their exits go
here (closing block).

## Wrap counts

Provisional, from `gh run list --branch <branch>` on 2026-10-18 before blocks 90 and 95 were pushed.

- **Runs**: one per pull request from #252 to #261, each at its first pushed head and green, none re-triggered.
- **Fix-backs**: none reached a pushed branch. Block 80's spec correction (`4aa1008`) landed before #261's run.
- **Cascaded rebases**: none.
- **Bodies called unreadable**: none at writing; the operator has not reviewed the stack yet.

## Next

- The holistic review, then the closing block 100: its findings, `BACKLOG.md` (the "Lot 1a" item deleted, lot 2
  without `merge`), this handoff corrected.
- The operator reviews and merges the stack. A release waits for "A copy before a migration that rewrites rows".
- Then lot 1b, from the same spec: the rings, the entry points and the check.
