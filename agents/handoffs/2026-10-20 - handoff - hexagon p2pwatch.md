# Handoff: the `p2pwatch` hexagon, lot 2 of the hexagonal architecture umbrella

Drafted by block 190 from the lot's block reports (#284, #285, #287 to #324), corrected by the closing block 210
from the reports of blocks 200 to 203 (#325 to #328), the holistic review and the operator's answers.

## State

Tier Spec lot. Spec `agents/specs/2026-10-19-hexagon-p2pwatch.md`, approved by the operator on 2026-10-19
(reviewed in `.reviews/lot2-spec.md`, gitignored: 0 critical, 12 major, 21 minor, each answered in the spec). It
carries out lot 2 of the umbrella spec `agents/specs/2026-10-18-hexagonal-architecture.md`.

One stack cut from `main` at `859b440` (lot 1b merged), still on the current `main` on 2026-10-20 (gh stack
#286). The spec's 19 blocks became 40 by splits (Pitfalls); the closing block split in five after the holistic
review (200 to 203, then 210), so the lot has 45 blocks.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #284 | `feat/logger-port` |
| 20 | #285 | `test/download-doubles-shared` |
| 30 | #287 | `refactor/amuleapi-session` |
| 35 | #288 | `refactor/one-amuleapi-session` |
| 40 | #289 | `refactor/reported-file` |
| 50 | #290 | `refactor/one-observation` |
| 55 | #291 | `refactor/observation-reads` |
| 60 | #292 | `refactor/node-id-catalog-and-source-points` |
| 70 | #293 | `refactor/node-id-notifications` |
| 75 | #294 | `refactor/node-id-ports` |
| 80 | #295 | `feat/run-crawler` |
| 85 | #296 | `refactor/asyncio-run-state` |
| 90 | #297 | `feat/crawler-control-use-cases` |
| 100 | #298 | `refactor/in-memory-status-board` |
| 110 | #299 | `feat/describe-node` |
| 115 | #300 | `feat/crawl-summary` |
| 117 | #301 | `test/crawl-summary-routes-on-fakes` |
| 120 | #302 | `refactor/catalog-file-counts` |
| 123 | #303 | `refactor/catalog-entry` |
| 125 | #304 | `feat/list-files` |
| 130 | #305 | `test/list-files-routes-on-fakes` |
| 135 | #306 | `test/files-rendering-on-fakes` |
| 140 | #307 | `refactor/sharing-period` |
| 143 | #308 | `refactor/file-history` |
| 145 | #309 | `refactor/domain-interval` |
| 146 | #310 | `feat/describe-file` |
| 147 | #311 | `test/describe-file-routes-on-fakes` |
| 148 | #312 | `test/file-page-rendering-on-fakes` |
| 149 | #313 | `test/file-page-history-on-fakes` |
| 150 | #314 | `feat/list-sources` |
| 160 | #315 | `feat/describe-source` |
| 163 | #316 | `refactor/source-name-history` |
| 164 | #317 | `feat/describe-source-name` |
| 165 | #318 | `test/source-pages-routes-on-fakes` |
| 170 | #319 | `feat/console-query` |
| 173 | #320 | `test/console-routes-on-fakes` |
| 175 | #321 | `refactor/webui-displays` |
| 180 | #322 | `refactor/role-ports` |
| 185 | #323 | `refactor/read-types-in-domain` |
| 190 | #324 | `refactor/ports-as-abcs` |
| 200 | #325 | `fix/holistic-code-and-tests` |
| 201 | #326 | `refactor/holistic-domain-types` |
| 202 | #327 | `fix/holistic-wiring` |
| 203 | #328 | `refactor/holistic-names` |
| 210 | closing | `docs/hexagon-p2pwatch-wrap` |

Nothing of the stack is merged. The lot changes what the crawler image runs (one shared amuleapi session, logger
names, two log lines gone), so a release is possible after the merge, but not before the backlog's "A copy before
a migration that rewrites rows" ships (spec, section "Backlog").

## What was built

- **The `Logger` port** (block 10): `ports/driven/logger.py` (`info`, `warning`, `error`), `StdlibLogger`, which
  takes the logger's name and wraps `logging.getLogger(name)`, and `FakeLogger` in `p2pwatch_testing`. The
  composition builds one per use case under its old module name; `logging` left `application/`'s ast-grep list.
- **The download doubles shared** (block 20): the five doubles of `test_run_download_cycle.py` in
  `p2pwatch_testing.application.download_fakes`, before any port they implement was renamed.
- **One amuleapi session that reopens itself** (blocks 30, 35, 200): `_call` opens the session under the login
  lock; a call after `close()` raises; a re-login on a `401` renews the token once for every call in flight, and
  none once the client is closed (block 200); `close()` takes the login lock. `connect` and `close` left the
  client ports and their three callers; the download loop shares the search session (one `POST /auth/login` per
  node).
- **Two observation types** (blocks 40, 50, 55): `ReportedFile` is what the network reports; `FileObservation`
  is a `ReportedFile` and its `observed_at`, stamped by `record_observations` from `wall_clock.now()` right
  before the write. Every catalog read returns it whole; `Sighting`, `ObservedFile` and `ReevalRow` are deleted.
- **The `node_id` through the calls** (blocks 60, 70, 75): the catalog's three writes, the source points' write
  and two reads, `EventEmitter.emit` and `Notifier.notify` take it; `AppriseNotifier` builds its two Apprise
  groups per `node_id` (`_groups_by_node_id`). `NodeIdReader`, `NodeIdWriter` and `NodeIdGenerator`
  (`Uuid4NodeIdGenerator`) replace `get_or_create_node_id`; `resolve_node_id` runs on them.
- **`RunCrawler`** (block 80): `application/run_crawler.py` resolves the `node_id`, emits `CrawlerStarted`,
  runs the startup re-evaluation and supervises the loops, each a callable taking the `node_id`. `CrawlerApp`
  builds, invokes it under the shutdown deadline, and closes.
- **The run state and the controls** (blocks 85, 90, 203): `AsyncioRunState` behind `RunStateWriter` (`pause`,
  `resume`, `shut_down`) and `RunStateReader`; `PauseCrawl`, `ResumeCrawl` and `RequestShutdown` behind
  `CrawlPauser`, `CrawlResumer` and `ShutdownRequester`, which the webui and `PosixProcess` call.
  `CrawlerControl` is deleted.
- **The status board** (block 100): `InMemoryStatusBoard` behind `ClientStatusWriter` and `ClientStatusReader`,
  holding no clock; the freshness rule `is_reading_fresh` in `domain/status_reading.py`.
- **One use case per page** (blocks 110 to 175): `DescribeNode`, `SummarizeCrawl`, `ListFiles`, `DescribeFile`,
  `ListSources`, `DescribeSource`, `DescribeSourceName` and `RunConsoleQuery`, each behind its driving port,
  over the driven readers `NodeStateReader`, `CoverageReader`, `CatalogFileReader`, `SourceReader` and
  `SqlExecutor`, which return domain types (`NodeState`, `TrackedDownload`, `CatalogEntry`, `FileHistory`,
  `DatedDecision`, `SharingPeriod`, `KnownSource`, `SourceNaming`, `SourceHistory`, `SourceNameHistory`,
  `QueryAnswer`/`QueryFailure`, `ConsoleDatabase`). `PeriodWindow`, the interval and `PAGE_SIZE`
  (`domain/paging.py`, block 200) are in `domain/`. `build_app` receives the driving ports and the values it
  renders with, no database path, reader or clock.
- **The route tests on fakes** (blocks 117, 130, 135, 147 to 149, 165, 173): each page's route tests run
  against a typed fake of its use case (`FakeCrawlSummarizer`, `FakeFileLister`, `FakeFileDescriber`, ...);
  sorting, filtering, paging and intervals are tested once, on the use case or the reader. Each block's report
  has the table of every old assertion and where it went (#320's table cites `test_sql_console.py`, since
  renamed `test_sqlite_sql_executor.py` by #321, same tests).
- **`views.py` becomes `displays.py`** (blocks 175, 200, 203): every view model a `<Thing>Display`, the source
  page's `SourceKeyDisplay` included (block 200), with the glossary's words (`FileHistoryDisplay`,
  `search_text`, `query_answers`, `client_name`, `filename`, `source_name`, block 203); the last webui
  exceptions in `tach.toml` gone (0 `[WARN]` on the crawler, from 66).
- **Role ports** (blocks 180, 203): `CatalogRepository` and `DownloadCatalogReader` become `ObservationWriter`,
  `ObservationReader`, `DecisionWriter`, `DecisionReader` and `CatalogScanReader`; local.db's repositories
  become `DownloadWriter`/`DownloadReader`, `SourcePointWriter`/`SourcePointReader`,
  `BackoffStateReader`/`BackoffStateWriter` and `PolicyFingerprintReader`/`PolicyFingerprintWriter`. Reads take
  the `read_` form.
- **The ports' own types in the domain** (blocks 185, 201): `DownloadCandidate`, `DownloadStatus`,
  `WaitingReason`, `FailureReason`, `RecordedReading`, `EarlierPoints`, `PublishedReading`,
  `MonotonicInstant`, then `SearchAnswer` (`domain/search/answer.py`) and `DownloadRequest`
  (`domain/download/request.py`). `TrackedDownload`'s waiting and failure reasons are the domain's enums (block
  201). The error contracts stay in their ports.
- **Every port an ABC** (block 190): `DiskSpace`, `Rng`, `Telemetry`, `MetricsSink` and `WakeHub` become
  `FreeSpaceMeter`, `JitterGenerator`, `EventEmitter`, `MetricsRecorder` and `Waker`, with their adapters,
  modules, fakes and parameters; the clocks, the four client ports, `Notifier` and `catalog_matching`'s `Matcher`
  become ABCs their implementers inherit; `SearchClient.channels` becomes a method; `@runtime_checkable` goes.
  The ast-grep rule `no-protocol-base` refuses a `Protocol` base under the crawler's, the matching's and the
  testing package's `src`.
- **The composed webui read and closed** (block 202): the full-mode wiring test GETs `/`, `/files` and `/node`
  and times a console query; the three catalog.db readers share one `ReaderProvider`; `ReaderProvider` is a
  context manager, and `UvicornServerThread` holds both providers in an `ExitStack` around serving, so the
  webui's read connections close on the thread that opened them.
- **The doubles and test names in the glossary's words** (blocks 202, 203): `FakeSourcePointStore`,
  `FakeDownloadStore` (its `record_queued` keeps the `target_id`), `FakeCatalogReader`; the persistence tests
  named after the operations they call.

## What an operator sees change

- **Logger names**: the startup lines `crawler started` and `download enabled` log under
  `p2pwatch.application.run_crawler` (block 80), written in `docs/migration-4x.md`. Every use case keeps its
  module's logger name (block 10).
- **Two log lines gone** with `_ensure_connected` (block 35): the info line `client <name> connected` and the
  warning `client <name> unreachable (...): reconnect backoff ...`. An unreachable amuled still logs
  `client <name> unreachable (...), client down, backoff ...`. Written in `docs/migration-4x.md` by block 210.
- **One amuleapi login per node**, not two (block 35).
- Nothing an operator configures changes: no config key, schema, route path, metric or notification
  (Acceptance 10 below).

## Acceptance

Re-run by block 210 at its tip on 2026-10-20, over `refactor/holistic-names` (`2226fba`).

1. Block 190: `grep -rnE "^class \w+\(.*\bProtocol\b" packages/crawler/src packages/matching/src
   packages/crawler_testing/src` prints nothing (21 lines on `main`). `class X(Protocol): ...` appended to
   `ports/driven/waker.py`: `uv run ast-grep scan` prints `error[no-protocol-base]`, exit 1; reverted, exit 0
   (block 190 injected it in each of the three trees).
2. Block 10: `import logging` in `application/edge_state.py` fails `ast-grep scan` (`error[application-imports]`,
   exit 1); `grep -rln "import logging"` on `application/` prints nothing (7 files on `main`).
3. Blocks 30, 35: `grep -rn "def connect\|def close"` on `ports/` prints nothing; the download-enabled wiring
   test asserts `api.logins == 1` (seen failing first, `assert 2 == 1`); the two client tests are #287's.
4. Block 80: the four `ast-grep run` patterns print nothing on `composition/app.py` (one call each at block
   75's tip). The check reads calls since the operator's answer (Operator decisions).
5. Block 70: `grep -rn "self\._node_id"` on `adapters/` prints nothing.
6. Block 203: the appendix's command prints only `now` (it printed `now` and `request_shutdown` from block 90 to
   block 202), since `RunStateWriter.request_shutdown` became `shut_down`.
7. Block 175: `tach check` prints 0 `[WARN]` lines on `packages/crawler/` (66 on `main`); `tach.toml` names lot
   2 nowhere.
8. Block 173 (rechecked at 175 and 210): the grep on `test_app*.py` prints nothing.
9. Block 175, re-run at 200, 202, 203 and 210: the render script over 26 GETs and 11 console POSTs gives the
   same 327,802 bytes on `main` and at the tip (sha256 `67c4edbc...`, both re-rendered by block 210); "Results"
   reworded in `console.html` at the tip makes the diff print the line.
10. Re-run by block 210 against `origin/main`: the `git diff -M100% ... '*/migrations/*' deploy/` command prints
    nothing; the `Route("...")` paths of `webui/app.py` are the same 15 (the file page's handler became
    `handle_file` in block 203); `adapters/driven/config/` has no diff, and the 13 `p2pwatch_` metric names
    (`domain/observability/policy.py`) are unchanged; `test_apprise_notifier.py` asserts the username
    `p2pwatch - titar-node-1` and the title `[titar-node-1] ...` (block 70).
11. The gate green at every block. CI's `build-and-verify` green on amd64 and arm64 at block 35 (run
    `39284101311`, at `def9448`), 80 (`39330674413`, at `e38f4ca`) and 175 (`39401254086`, at `f1a6680`): each
    shows compose "7 passed, 1 skipped" (the expected prebuilt skip) and the daemon suites "6 passed" on both
    architectures. Locally, the api, download and orchestration suites passed (6 tests) against a throwaway
    `p2pwatch-amule:main` at blocks 35, 75, 80 and 175.

## Departures from the spec

- **Splits**: blocks 30, 50, 80, 90, 110, 120, 130, 140, 145, 147, 160, 163 and 170 split at a bound, and 185
  was added (block 180 found port-owned types). The closing block split in 200, 201, 202, 203 and 210 after the
  holistic review's 39 findings. Each is a `(Corrected ...)` row of the block table.
- **Size exemptions**: blocks 10 (427 lines, 30 files), 20 (540, 5), 40 (270, 23), 60 (556, 30), 70 (227, 20),
  180 (1,210, 63), 185 (427, 45), 190 (1,092, 65), 203 (399, 41).
- Block 10: `StdlibLogger` takes the logger's name; three wiring assertions on a record's name, not one;
  `WorkerDeps.observation_logger`.
- Block 60: the loops' entry points take the `node_id` already, so block 80 only moved the call. Block 70:
  `status_loop` takes it too.
- Block 80: `arm_shutdown_bound` is an argument of `RunCrawler.run`; the re-evaluation is a callable taking the
  `node_id`; a closure, not `functools.partial`, which `application/`'s list does not hold.
- Block 100: `is_reading_fresh` takes the reading's age; `STATUS_PERIOD` moves with it.
- Block 110: `TrackedDownload` drops `size_bytes`; `NodeState`'s `node_id` and `created_at` are optional.
- Block 115: `CoverageReader` returns each target's tiers, the domain's `coverage_of` computes the coverage;
  `SummarizeCrawl` receives the target ids; `TargetCoverageRow` became `TargetCoverageDisplay`.
- Block 123: the reader takes `limit`/`offset`. Block 125: no `ListedFile`, `FileListing` holds `CatalogEntry`s.
- Block 140: `SharingPeriod` also holds the role, the contact point and connectability. Block 143:
  `read_file_history` takes `since`/`until`; `FileHistory` holds the key, size and latest observation.
- Block 145: `parse_instant` and the presets' labels stay in the webui. Block 146: `FileDescription.explanation`
  is `catalog_matching`'s `Explanation`.
- Block 150: its route tests in the block itself. Blocks 160, 163: `SourceNaming`, `best_filename_by_file` on
  both histories, the context key `source_name`.
- Block 170: `ConsoleDatabase` in the domain; `QueryAnswer`/`QueryFailure` a union. Block 175: `ConsoleResult`
  and `ConsoleRow` became `QueryAnswerDisplay` and `QueryRowDisplay`.
- Block 180: the five catalog ports share `ports/driven/catalog.py`; `FakeCatalogReads` stays one fake, two reads
  raising (`NoReturn`).
- Block 185: every driven port's own types moved, not the read ports' only.
- Block 190: the renamed ports' modules, fakes and parameters follow the class; `ports/driven/telemetry.py`
  keeps its name; `SearchWorker.channels` stays a property.
- Block 200: `PAGE_SIZE` in a module of its own, `domain/paging.py`, since a page size is not an interval.
- Block 202: no assertion on `wired-node` in `/node` (the node page shows `None` for a configured id, a backlog
  entry); `ReaderProvider` a context manager, from the operator's answer.
- Block 203: `FakeSourcePointStore` and `FakeDownloadStore`, not the review's `FakeSourcePoints` and
  `FakeDownloads`, after `FakeNodeIdStore`; `handle_file_detail` became `handle_file`, like `handle_source`.

## Spec corrections

Each a `(Corrected 2026-10-19: ...)` or `(Corrected 2026-10-20: ...)` in the lot's spec: the block table's
splits and size exemptions; Acceptance 4 (ast-grep for the grep, block 80), 6 (ast-grep for the `awk`, then
closed at block 203), 3, 7, 8, 9 and 11 (the blocks they close at); `FileListing` holding `CatalogEntry`s;
`shut_down` in the control section (block 203); the block 175 of the deprecated edges (block 200, `8021b18`);
the accepted limit of `/targets/{id}` (block 210). Block 10 marked the earlier specs' corrections listed in the
spec's section "Corrections of earlier specs". Block 210 added two paragraphs to the spec's section "Backlog".

## Tests pruned or moved

- Block 35: the connect and reconnect tests, covered by an unreachable search or `downloads()`;
  `test_download_fakes.py`.
- Blocks 117 to 173: every route assertion kept on the fake, moved to the use case's or the reader's tests, or
  dropped as a duplicate, each listed in its block's table. Two gaps the old route tests alone covered were
  closed (block 149: the explainer's duration and bitrate; block 165: every period kept on every page), and one
  in the wiring test (block 170: each console database mapped to its path). Two the review found lost were
  closed at Wrap: the interval clamp (block 200, on the three describers) and the console's clock wiring (block
  202, a timed query's elapsed milliseconds above zero).
- Block 180: three structural port tests and three adapter tests asserting a structural match; block 190: the
  five structural tests left in `tests/ports/driven/`, `@runtime_checkable`'s `isinstance` test among them. An
  ABC is checked by mypy on its inheriting class.
- Block 202: `FakeDownloadRepo.waiting`, which no test read.

## Class 1 fixes

- Block 40: an em dash in `ObservedFile`'s docstring. Block 50: `test_migration_0007.py`'s `observation`.
- Block 85: an unused counter of a fake loop. Block 110: em dashes in `test_local_read.py`.
- Block 140: "source range" in a comment. Block 165: `_SECOND`, unused.
- Block 173: `close_test_connections`'s thread filter, dead once the console's queries moved to a fake.
- Block 180: `SqliteCatalogRepository`'s docstring on the `node_id`. Block 190: `FakeSearchClient`'s module
  docstring naming `connect`.
- Block 200: a missing blank line in the new client test (`6a7f3af`), which failed `format-check` at the block's
  own tip, found by gating each block's tip after the split.

## Operator decisions

Taken during Act and Wrap, each from a class 2 question or a finding the lead brought:

- Block 80: Acceptance 4's grep matched the logger name the composition hands `RunCrawler`. Operator: "C'est pas
  très malin comme vérification non ? On a ast-grep en plus". The check reads calls with ast-grep.
- Block 110: of two tests trimmed for the size bound, one was restored (`197194a`) by the operator's rule that
  the bound is no reason to delete a test.
- Block 160: the operator chose the name `SourceNaming`.
- Blocks 180, 190, then 203: `request_shutdown` declared by `RunStateWriter` and `ShutdownRequester`
  (Acceptance 6). Option (b): the driven operation becomes `shut_down`, a state change beside `pause` and
  `resume`.
- Block 203: `CatalogScanner`, neither a `Writer` nor a `Reader`, renamed `CatalogScanReader`.
- Block 202: the webui's reader connections left to the garbage collector. Operator: "implémenter l'interface
  ContextManager serait intelligent", then "ok" on the design (`ReaderProvider` a context manager, held by
  `UvicornServerThread`).
- Wrap: the ast-grep gate hole. The operator refused a check pairing the rules and their tests as "un pansement";
  the backlog entry asks for a design that fixes the cause.
- Wrap: `/node` showing `None` for a configured node id, already so on `main`, goes to the backlog.

## Pitfalls

- **A stale `.pyc` runs old bytecode**: an edit that keeps a file's size within the same second (a mutation
  flipped and restored by `sed`) leaves Python on the old code, so the gate fails on code that reads right
  (blocks 10, 180). Clear every `__pycache__` before a gate run.
- **Serena's renames are partial and can land at shifted offsets**: `rename_symbol` reached 1 to 8 references
  (blocks 40, 175, 190). In block 190, renames run back to back right after the server started wrote some edits
  at shifted offsets (`import ClientUnreachableError` became `impoFreeSpaceMeterUnreachableError`,
  `RecordingWakeHub()` became `ReFakeWaker`); the tree was reset and the renames redone with word-bounded `sed`.
  In block 203 the first rename after each start reached part of the uses (`FileDetailDisplay`: its definition
  only; `request_shutdown`: not `AsyncioRunState` nor the call in `RequestShutdown`; `CatalogScanner`: not
  `SqliteCatalogRepository`). Read the diff after each rename, then `git grep -w` the old name; `AGENTS.md`'s
  Gotchas carry the rule.
- **A word-bounded substitution also hits module paths**: `\bobservation\b` matched `domain.observation`
  (block 40), `\btelemetry\b` `ports.driven.telemetry` (block 190); protect the path first.
- **`ast-grep test` passes with no rule**: a test file whose rule id has no rule prints `Configuration not found!`
  and exits 0 (block 190, as lot 1b found; the holistic review reproduced it). Watch a new rule's test fail by
  narrowing the written rule. A backlog entry.
- **A `StrEnum` compares equal to its text**: a test of an enum field asserts with `is` (block 201).
- **SQLite lets only the opening thread close a connection**: the webui's read connections, opened on its
  thread, left 2 `ResourceWarning: unclosed database` once a test read pages through the composed app, and
  `close_test_connections` could not close them (block 202).
- **The webui renders Jinja under `StrictUndefined`**: a template left reading a renamed field returns a 500,
  which the render diff shows (block 203).
- **No test tells one shared connection from two** without private state, `monkeypatch.setattr` being banned
  (block 202): the shared provider is asserted through the coverage it reads.
- **`gh run watch` can exit before the run's jobs end** (met by the lead during the lot): read the run's
  conclusion with `gh run view` before reporting it green.
- **The 6.1 GB node catalog fills `/tmp`** (a tmpfs) when copied there (block 55): read it in place, `mode=ro`.
- **The block splits**: the estimates left out the tests, the shared fakes and the call sites that gain a
  keyword, so 13 blocks split and the stack grew from 19 blocks to 40, then 45 with the closing block's split.
  Counting the files before any code (blocks 90, 110, 140, 160, 170) caught most splits early.
- **A rename that git sees below 50 % similarity** counts as a deletion and an addition (blocks 85, 145, 170):
  keep a moved module's name, or its content close, when the bound is near.
- **Shared doubles fall under the crawler's coverage** once in `p2pwatch_testing` (block 20): a guard no test
  reaches fails the gate.
- **Gate each block's tip after a split**, not only the top: block 200's own tip failed `format-check`.

## Not validated

- `compose_integration` locally: its completion test fails under Docker Desktop by design; CI's
  `build-and-verify` ran it on both architectures in every run, blocks 200 to 203 included.
- No integration suite ran locally for blocks 190 to 203.
- No page was driven by hand on a running node; the render checks (blocks 110 to 210, Acceptance 9) compare the
  HTML of seeded databases only.
- A real Discord webhook with the per-`node_id` groups (block 70).
- The webui's read connections closing at the stop on a running node (block 202): seen in the tests only.
- The deployed node never ran the stack.
- **TDD evidence the holistic review found missing**, each not watched failing:
  - block 60 (#292): its new tests (`test_each_write_stores_the_node_id_its_call_gives`,
    `test_a_task_records_its_observations_under_the_node_id_the_tasks_run_with`): the report quotes calls, no
    failure line of their own;
  - block 70 (#293): `test_a_node_keeps_its_groups_and_another_node_gets_its_own`, the Apprise groups kept per
    `node_id`;
  - block 75 (#294): the refused second `record_node_id`, likely a characterization that passed at once;
  - block 135 (#306) and block 148 (#312): one negative path each for about 15 and about 8 rewritten rendering
    tests, the others not watched failing;
  - block 180 (#322): the raising methods of `FakeCatalogReads` (now `FakeCatalogReader`).

## Holistic review

By `lot2-holistic` over `git diff origin/main...origin/refactor/ports-as-abcs`, top `1bee7f1`
(`.reviews/lot2-holistic.md`, gitignored): 0 critical, 6 major, 33 minor. Every finding was fixed in the lot but
4 (a backlog entry), 12 (an accepted limit) and part of 28 and 30 (refused).

1. MAJOR, Acceptance 6 fails on `request_shutdown`: fixed (block 203), the operator's option (b), `shut_down`.
2. MAJOR, no test checks a retraction's `node_id`: fixed (block 200), seeded under another node.
3. MAJOR, no test checks the interval clamp or an inverted interval before the readers: fixed (block 200), a
   30-day and an inverted request on each describer.
4. MAJOR, `ast-grep test` passes a test whose rule does not exist: a `BACKLOG.md` entry, "The ast-grep rule tests
   bound to their rules by design" (the operator refused a pairing check).
5. MAJOR, the source page's template receives a `SourceKey`: fixed (block 200), `SourceKeyDisplay`.
6. MAJOR, `architecture.md`'s mermaid label calls the ports protocols: fixed (block 210), `ports/ · ABC`.
7. The re-login on a `401` after `close()`: fixed (block 200).
8. `SearchAnswer` and `DownloadRequest` owned by their ports: fixed (block 201), moved to the domain.
9. `CatalogScanner` neither a `Writer` nor a `Reader`: fixed (block 203), `CatalogScanReader`, the operator's
   ruling.
10. `TrackedDownload`'s reasons typed as text: fixed (block 201), the domain's enums.
11. Two log lines gone, not in `docs/migration-4x.md`: fixed (block 210), in the 5.0 log paragraph.
12. `/targets/{id}` runs two catalog-wide counts it discards: an accepted limit, the price of one use case per
    page, written beside the `/targets/{id}` decision in the spec (block 210).
13. Two catalog.db read connections per thread: fixed (block 202), one shared `ReaderProvider`.
14. No test serves a read page through the composed app: fixed (block 202), `/`, `/files` and `/node`; the
    `wired-node` assertion left out, since `/node` shows `None` for a configured id (a `BACKLOG.md` entry).
15. The console's clock wiring lost: fixed (block 202), a timed query in the wiring test.
16. `FakeDownloadRepo.record_queued` drops its `target_id`: fixed (block 202), `waiting` deleted.
17. `AGENTS.md`'s Serena gotcha cites a deleted import: fixed (block 210), now the rule that a double two test
    modules share lives in `p2pwatch_testing`.
18. `AGENTS.md`'s new gotcha is lot history: fixed (block 210), the rule kept, the anecdote in Pitfalls above.
19. The glossary has no `response model` row: fixed (block 210).
20. `architecture.md`'s "Cas d'usage" row lists the loops: fixed (block 210), a "Boucles" row and a "Cas
    d'usage" row.
21. Stale docstrings in `ports/__init__.py` and `tests/ports/__init__.py`: fixed (block 203).
22. `webui/app.py`'s false module docstring: fixed (block 203).
23. `_start_webui`'s false docstring: fixed (block 203), it says why each shared object is safe across threads.
24. `download_loop`'s stale docstring: fixed (block 203), it names `RunCrawler`.
25. Old operation names in `download_repository.py`'s docstring and the `# CatalogReader` header: fixed (block
    203).
26. The search text called `query`: fixed (block 203), `search_text`.
27. Bare `name` fields: fixed (block 203), `client_name`, `filename`, `source_name`.
28. `file detail`: fixed (block 203), the orphan header deleted, `FileHistoryDisplay`, `file_history.html`,
    `source_history.html`. Refused for the visible heading "File detail": page text an operator reads, and the
    lot changes no page (Acceptance 9).
29. `entry`, `dec`, `seg`, `t, ti`: fixed (block 203).
30. The console's answer called `result`: fixed (block 203), `query_answers`. Refused for the visible text
    "Results", for 28's reason.
31. Doubles named after deleted ports: fixed (block 203), `Store`, after `FakeNodeIdStore`.
32. Test names and headers using old operation names: fixed (block 203).
33. Docstrings deferring to a decision id: fixed (block 203).
34. `PAGE_SIZE` defined four times: fixed (block 200), `domain/paging.py`.
35. The spec contradicts itself on block 170: fixed (block 200, the lead's `8021b18`).
36. Acceptance 11's runs not cited: fixed (block 210), Acceptance 11 above.
37. TDD evidence missing: stated (block 210), under Not validated.
38. Report hygiene: fixed in this handoff (block 210), #320's path corrected above, #324's "1,500 lines" clause
    dropped.
39. Long dashes in the lot's areas: fixed (block 203).

## Wrap counts

From `gh run list --branch <branch>` and `gh pr view` on 2026-10-20, before block 210 was pushed, over the 44
blocks before the closing one.

- **Runs**: 51. Each pull request from #284 to #328 has one run at its current head, attempt 1, green (44, with
  `build-and-verify` on amd64 and arm64). The 7 others:
  - 3 cancelled by a second push before the block's report, no fix-back: #299 (`16da2d8`), #300 (`368f2b2`),
    #313 (`654eedc`, the lead's spec commit, before `694f00e`, a gap closed at the lead's request);
  - 2 cancelled, re-triggered by the cascade below;
  - 2 green at an earlier head, superseded by the fix-backs below: #327 at `6382044` (`39416203304`), #328 at
    `6fd472d` (`39418059918`).
- **Fix-backs**: 2.
  - Block 202 (#327, `f751c3e`): the webui's reader connections, the operator's answer, after #327 and #328 had
    run green. Run `39422429864`, green.
  - Block 203 (#328, `fd29480` to `2226fba`): the operator's rulings on Acceptance 6 and `CatalogScanner`, after
    its first run. Run `39422959988`, green. Nothing stood above it.
- **Cascaded rebases**: 1: #328 onto `f751c3e` (`6fd472d` became `16bab7a`; `git range-diff` shows only the
  docstring commit's context changed). It re-triggered 2 runs at `16bab7a` (`39422260638`, `39422460575`), both
  cancelled by the fix-back's push. Blocks 201 and 202 were rebased onto block 200's class 1 fix before any of
  the three was pushed, which triggered no run.
- **Runs re-triggered** by fix-backs and cascades: 4 (the two fix-backs' runs, the cascade's two), fewer than the
  44 blocks.
- **Splits**: 13 blocks of the spec's table, 185 added, and the closing block in five. **Exemptions**: nine.
- **Bodies called unreadable**: none at writing; the operator has not reviewed the stack yet.

## Next

- The operator reviews and merges the stack, after the lead rebases it onto `main` if `main` moved.
- **"A copy before a migration that rewrites rows" ships next**: `BACKLOG.md` requires it before the next
  release. Only then does the lead propose a release, if the operator wants one: this lot changes the image.
- Then "Contract tests for the fakes", which waited for the ports' final shape, and lot 3 of the umbrella.
- Two backlog entries from this lot: the node page's configured node id, and the ast-grep rule tests bound to
  their rules by design.
