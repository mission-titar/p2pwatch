# Hexagonal architecture, lot 2: the `p2pwatch` hexagon

- Date: 2026-10-19. Status: approved by the operator on 2026-10-19, settled in Discuss with them, reviewed
  (`.reviews/lot2-spec.md`: 0 critical, 12 major, 21 minor, all answered here).
- Tier: Spec, one lot and one stack (the operator's choice).
- Origin: lot 2 of the umbrella spec `agents/specs/2026-10-18-hexagonal-architecture.md`, whose decisions this one
  applies without restating them. It inherits section 7 of `agents/specs/2026-10-13-descriptive-names.md` and the
  section "For the architecture lot" of `agents/specs/2026-10-17-serena-and-the-language-servers.md`. Section
  "Corrections of earlier specs" lists where it departs from them.
- What an operator sees change: some logger names (listed in `docs/migration-4x.md`), nothing else.
- Paths are under `packages/crawler/src/p2pwatch/` unless noted. The measurements are in the appendix.

## Summary

- **The core stops doing I/O outside a port**: the amuleapi adapter manages its own session, and `application/`
  logs through a `Logger` port.
- **The composition only builds**: a `RunCrawler` use case runs what `CrawlerApp.crawl` runs today, and the
  `node_id` reaches the adapters through the calls, not their constructors.
- **The webui reads through use cases**: one use case per page, each behind its own driving port, over driven read
  ports that return domain types. The route tests run against fakes of the use cases.
- **Every port is an ABC, phrased by its consumer's need**: the catalog's and local.db's repositories split into
  `Writer` and `Reader` ports, the other ports are named after who acts, and no `Protocol` is left in the hexagon.

## Conventions this lot sets

Each goes into `AGENTS.md`'s Naming section in the block that first applies it.

- **A port over stored state is a `<Thing>Writer` or a `<Thing>Reader`**, never both: both databases, the status
  board, the run state. Why: command-query separation applied to the ports; a fake implements only what its
  consumer calls, since an ABC forces every abstract method; the operator wanted one convention with no exception,
  even for a store with a single consumer.
- **A port to an outside system or a service keeps a capability name**: `DownloadClient`, `MonotonicClock`,
  `Waker`, `SqlExecutor`. Why: its operations act on that system rather than read back what we wrote; interface
  segregation would split it only for two consumers, and none has two. A later need splits it then.
- **`Writer`, not `Recorder`**: local.db's ports overwrite (`set_state`, `save_backoff_states`), and the word must
  fit both. A `Writer`'s operations keep their verbs (`record_observation`, `set_state`).
- **A `Reader`'s operations start with `read_`** (`iter_` for an iterator); a predicate keeps `is_` or `has_`. A
  driving port's operation is its use case's verb (`list_files`). Why: the tree mixes verbs and nouns on its
  reads; one form, and a reader can tell which side of the hexagon a call is on.
- **A driving port's response model is named from its use case's verb**: `ListFiles` returns a `FileListing` (Corrected
  2026-10-19: of `CatalogEntry`s, no `ListedFile`), `DescribeFile` a `FileDescription`, `SummarizeCrawl` a `CrawlSummary`. Why: the type says which
  operation produced it, with no technical suffix.
- **A driven read port returns domain types only.** What a page reads that the domain does not model yet is a
  missing domain concept, added to `domain/` (below), never a type owned by the port. Domain types carry their
  instants as `datetime`, never as text: formatting is the HTTP adapter's. Why: the core handles only types of its
  model (the repositories of DDD return objects of the domain's language); a read model owned by the port, as
  CQRS has it, would bypass the domain, which the operator refused.
- **A driving port returns its response model**, defined in its port's file: the domain objects the use case read,
  plus what belongs to the request and not to the domain (paging, the page's counts, the resolved interval and its
  `now`). Every driving port has one, even where it would only wrap a domain object (`/node`): one rule. This is
  the use case's output data in Clean Architecture's terms. The HTTP adapter turns it into `<Thing>Display` view
  models, in `displays.py` (section 7 of the descriptive-names spec). A type both sides use (`PeriodWindow`, the
  interval) lives in `domain/`. Why: D8, a driven adapter cannot see a driving port, and paging is not a domain
  concept.
- **A use case implements a driving port, but the root of the crawler's graph**, `RunCrawler`, which the
  composition root invokes once it has built the graph (below).

## The session and the logger

### One session that reopens itself (D10)

`AmuleApiClient` already serializes its login under `_connect_lock`, and `open()` already tolerates an amuled not
yet listening. What is left:

- `_call` opens the session itself when it has none, under the same lock, instead of raising "call connect()
  first". `connect` becomes private.
- `close()` marks the client closed, and a call after it raises instead of logging in again: an overrun shutdown
  must not open a session it will never revoke.
- The re-login on a `401` takes the lock too, and logs in only if no other call renewed the token meanwhile: with
  three loops on one session, a daemon restart costs one login, not one per call in flight.
- `connect` and `close` leave `SearchClient`, `StatusClient` and `DownloadClient`; their three callers in
  `application/` go (`search_worker.py`, `status_loop.py`, `run_download_cycle.py`), and so does the search
  worker's `_connected` flag.
- **One session per node**: the download loop stops building its own `AmuleApiClient` and shares the search one.
  Why: one login, one lock, one count of rejected tokens against amuleapi's lockout; a REST session serves
  concurrent calls, and the second session was left from EC.

### The `Logger` port (D9)

- `Logger` (`ports/driven/logger.py`), with `info`, `warning` and `error`, each `(message: str, *args: object)`:
  the three levels `application/` uses. `StdlibLogger` (`adapters/driven/stdlib_logger.py`) wraps a
  `logging.Logger`. `FakeLogger` in `p2pwatch_testing` keeps each call's level and formatted message.
- The composition builds one `StdlibLogger` per use case, named as its module's logger is today
  (`p2pwatch.application.<module>`), so an operator's filters keep working; a wiring test asserts one record's
  `name`, which `FakeLogger` cannot see.
- The six test files that read these logs through `caplog` read the `FakeLogger` instead.
- `logging` leaves `application/`'s list in `ast-grep-rules/application-imports.yml`.

Why a port and not the observability events: D9 settled a logging port; a log line is a diagnostic for the
operator, an event is a fact the policy routes to metrics and notifications.

## The composition only builds

### `RunCrawler`

`CrawlerApp.crawl` runs behaviour today: it resolves the `node_id`, emits `CrawlerStarted`, runs the startup
re-evaluation, then `supervise_loops`. That behaviour moves to `RunCrawler` (`application/run_crawler.py`), which:

1. resolves the `node_id` (`resolve_node_id`);
2. emits `CrawlerStarted`;
3. runs `reevaluate_if_policy_changed`;
4. launches the loops with that `node_id`, under `supervise_loops`, until the stop.

`RunCrawler` receives the built loops (callables taking the `node_id`), the ports its steps need, and
`arm_shutdown_bound`. The loops' dependencies (`WorkerDeps`, `StatusLoopDeps`, `DownloadLoopDeps`) carry no
`node_id`, so the composition builds them before it is known.

`CrawlerApp` keeps `CrawlerRunner` (lot 1a's decision: what it builds depends on the config the command line just
read). It loads the config through its adapter, builds every adapter, the loops and `RunCrawler`, invokes it, and
closes the resources. It keeps the shutdown deadline (`asyncio.timeout` around the call and the close, whose
rescheduling reads the event loop's time) and the progress lines of the stop, which `print` (refused in the core
by `core-builtins.yml`).

Why: a composition root composes, resolves the root object and invokes it, then releases (Seemann's Register,
Resolve, Release), and it may be invoked on demand with runtime data, as ASP.NET's controller activator is per
request. `RunCrawler` is that root, invoked by the composition root it was built by, so it needs no driving port;
a port only the composition calls would make the composition a driving actor, which it is not. The loops and the
startup steps are internal steps of "run the crawler", whose actor is the operator (`crawl`); a loop sleeping on
`MonotonicClock` consumes a driven port, so time is not a driving actor here.

### The `node_id` through the calls

Three adapters receive the `node_id` at construction (`SqliteCatalogRepository`, `SqliteSourceRepository`,
`AppriseNotifier`), so it must exist before the graph is built, and only behaviour produces it. It leaves their
constructors and travels with the calls:

- the catalog's writes: `record_observation`, `record_decision`, `record_retraction`;
- the source points: `record_readings`, and the two reads that keep this node's points only, today's
  `earlier_points` and `has_points_before`;
- the notifications: `EventEmitter.emit(event, node_id)` (15 call sites in 6 modules), then `Notifier.notify`.
  `AppriseNotifier` builds its two Apprise groups on the first notification for a `node_id` and keeps them for
  that `node_id`: Apprise hands its asset, whose `app_id` is the Discord username `p2pwatch - <node_id>`, to each
  plugin when a URL is added, so the groups cannot be shared across ids. The notifier's tests assert that username.

Why: injecting runtime data into a constructor is the smell, and passing it through the method calls is its first
remedy (Seemann and van Deursen, *Dependency Injection Principles, Practices, and Patterns*, 2019; van Deursen,
"Injecting runtime data into components is a code smell", 2015). The `node_id` is domain data: the catalog records
which node observed what. An abstract factory per adapter would treat the symptom with three ports more; a context
provider would leave a temporal coupling no type shows.

### Creating the `node_id`

`get_or_create_node_id` reads and writes in one operation. It splits into `NodeIdReader.read_node_id()` and
`NodeIdWriter.record_node_id(node_id, created_at)`; the new id comes from a capability port, `NodeIdGenerator`
(`new_node_id()`), whose adapter `Uuid4NodeIdGenerator` holds today's `uuid.uuid4()`. `resolve_node_id` returns the
configured id, else the stored one, else generates and records one. Why: the core may not call `uuid4` (entropy,
D9), and `Rng` would then mix two needs.

## One observation

Four types describe one observation today: `FileObservation` (written, no instant), `Sighting` (read by the
webui, its instant an ISO string), `ObservedFile` (filename and size, for the download loop) and `ReevalRow` (for
the re-evaluation).

- **`ReportedFile`** is what the network reports, with no instant: today's `FileObservation`, renamed, with the
  variables holding one (`observation` becomes `reported_file`). The amuleapi mapper builds it, `SearchAnswer`
  carries it.
- **`FileObservation`** is a `ReportedFile` and its `observed_at: datetime`. `record_observations` builds it from
  `wall_clock.now()` right before the write, as `AGENTS.md`'s invariant asks, and every read returns it whole,
  `raw_meta` included.
- `Sighting`, `ObservedFile` and `ReevalRow` are deleted.

Why two types and not one: amuleapi does not date its results, and the client reads them in one batch at the end
of a search, so "when the crawler learned of the file" is the only instant either side knows, and the use case
reading it keeps a single stamping policy. Without an instant, what the network says is a report, not an
observation. Decoding `raw_meta` on every read costs about 0.1 s over the whole deployed catalog (appendix).

## The webui reads through use cases

### One use case per page (D7, D8)

| Page | Use case | Driving port and operation | Returns |
|---|---|---|---|
| `/` | `SummarizeCrawl` | `CrawlSummarizer.summarize_crawl` | `CrawlSummary` |
| `/files`, `/targets/{id}` | `ListFiles` | `FileLister.list_files` | `FileListing` |
| `/files/{id}` | `DescribeFile` | `FileDescriber.describe_file` | `FileDescription` |
| `/sources` | `ListSources` | `SourceLister.list_sources` | `SourceListing` |
| `/sources/{id}` | `DescribeSource` | `SourceDescriber.describe_source` | `SourceDescription` |
| `/sources/name` | `DescribeSourceName` | `SourceNameDescriber.describe_source_name` | `SourceNameDescription` |
| `/node` | `DescribeNode` | `NodeDescriber.describe_node` | `NodeDescription` |
| console | `RunConsoleQuery` | `ConsoleQueryRunner.run_console_query` | `ConsoleQueryOutcome` |

`/targets/{id}` is the files page filtered on one target (`handle_target` calls `list_files(target=...)` and
renders `files.html`), so it calls `ListFiles` with that target. A route makes one call and receives one response
model; the assembly the routes do today (the dashboard reads the coverage, the node state, the run state and the
client status) moves into the use case. `DescribeFile` calls today's `MatchingExplainer`
(`application/matching_read.py`), an internal step with no port.

**The interval and `now`**: `interval.py` moves to `domain/` in the first block that resolves an interval in a use
case (`DescribeFile`). The route parses the query string into the requested bounds; the use case resolves the
interval on its `WallClock`, turns it into a `PeriodWindow` with `source_period_gap` (which the use case receives),
and returns the interval and its `now` in the response, from which the HTTP adapter renders the selector.

`build_app` receives the eight driving ports of the table, the three control ports, and the values it renders
with: `templates_dir`, `static_dir`, `amule_url` and the targets (their titles, for display). No database path, no
reader, no clock.

### The driven read ports

| Port | Operations | Read by |
|---|---|---|
| `CatalogFileReader` | `read_catalog_entries`, `read_matched_and_total_file_counts`, `read_file_count_by_tier`, `read_file_history` | `ListFiles`, `DescribeFile` |
| `SourceReader` | `read_known_sources`, `read_source_count`, `read_source_history`, `read_source_name_history`, `read_sharing_periods` | `ListSources`, `DescribeSource`, `DescribeSourceName`, `DescribeFile` |
| `CoverageReader` | `read_target_coverage` | `SummarizeCrawl` |
| `NodeStateReader` | `read_node_state` | `SummarizeCrawl`, `DescribeNode` |
| `SqlExecutor` | `execute` | `RunConsoleQuery` |

`CatalogFileReader`, not `FileReader`, which reads as reading a file on disk. Their SQLite adapters keep today's
read-only connections (`ReaderProvider`, one per thread).

### The domain concepts the pages read

The 13 types the readers import from `views.py` leave it. `PeriodWindow` goes to `domain/`; the others become
domain concepts, or give way to the domain type they copy with text instants:

| Today | Domain type | What it holds |
|---|---|---|
| `FileRow` | `CatalogEntry` | the file's key, its size, its latest `FileObservation`, its current decisions by target |
| `FileDetail` | `FileHistory` | its observations over the interval, its decisions, its known filenames |
| `SourcePeriodView` | `SharingPeriod` | a source, a file, its first and last reading, the bytes received, the node that read them |
| `SourceRow` | `KnownSource` | the source's key, its latest `source_name`, its latest reading, its file count |
| `SourceDetail` | `SourceHistory` | its successive `source_name`s, its `SharingPeriod`s |
| `NameDetail` | `SourceNameHistory` | the sources that carried the name, their `SharingPeriod`s |
| `NodeState` | `NodeState` | its id, its creation, its `TrackedDownload`s, its backoffs |
| `TargetCoverageRow` | `TargetCoverage` | the target, its status, its best tier, its file count; the title and the shown text go to its `Display` |
| `DownloadRow` | `TrackedDownload` | a tracked download (the glossary's `tracked`): file, target, state, instants, waiting or failure reason |
| `DecisionView` | `DatedDecision` | a `DecisionRecord` with its `decided_at` and its `node_id` |
| `FileDecision`, `BackoffRow`, `TimelineRow` | deleted | `DecisionRecord`, `BackoffKey` with `BackoffState`, `FileObservation` |

`DatedDecision` is a type of its own because `DecisionRecord` (in `catalog_matching`) compares its three fields only,
for the anti-redundancy: an instant and a node would break that equality. Each page block adds the concepts its
page reads; `views.py` keeps only view models and becomes `displays.py`.

The names section 7 left to this lot go with them: `query` becomes `search_text`, the `_PAGE_SIZE` alias goes,
`_ISO` goes with the text instants, and the fields `file_name` and `name` become `filename` or `source_name`. The
dead `{% else %}` at `templates/sources.html:25-26` goes with the sources' block.

### The control and the status board (D6)

- **Control**: three use cases, `PauseCrawl` (`CrawlPauser`), `ResumeCrawl` (`CrawlResumer`) and `RequestShutdown`
  (`ShutdownRequester`), over `RunStateWriter` (`pause`, `resume`, `request_shutdown`). `LoopCrawlerControl`
  becomes `AsyncioRunState`, which also implements `RunStateReader` (`is_paused`), read by `SummarizeCrawl`; until
  that use case exists, the dashboard reads `RunStateReader` under a deprecated edge. `PosixProcess` calls
  `ShutdownRequester`. `CrawlerControl` is deleted. Why: a use case is named after one operation.
- **Status board**: `StatusBoard` leaves `application/` and becomes a driven adapter, `InMemoryStatusBoard`, behind
  `ClientStatusWriter` (`publish(client_name, reading, published_at)`) and `ClientStatusReader`
  (`read_readings`, each with its `published_at`, a `MonotonicInstant`). It holds no clock: the status loop gives
  the instant. The freshness rule (`READING_FRESH_FOR`) becomes a domain function, which `SummarizeCrawl` calls
  with the `MonotonicClock` it holds (`AsyncioMonotonicClock.now` needs no running loop, so the webui's thread can
  read it). `StatusReadings` is deleted. Why: two use cases sharing mutable state must see it through a port, and
  a store decides no time, as persistence already does.

Umbrella D6 made these driving ports; with one use case per page, the webui reads them through `SummarizeCrawl`,
so they are driven ports a use case consumes.

### The route tests

`tests/adapters/driving/webui/test_app.py` (2,663 lines, 114 tests) runs every route through the real readers on
fixture databases. Each page's routes are first switched to their use case, the old tests still passing over the
real use case and readers; a second block then rewrites those tests against a typed fake of the use case, which
checks the parameters' decoding and the rendering only. The assertions on sorting, filtering, paging and
intervals move to the use case's tests (with fake readers) or to the reader's tests (on the fixture databases),
and the second block's report lists each old assertion and where it went. Why: a driving adapter's test receives
a fake of its use case (D7), and a page's logic is tested once rather than twice.

## Ports as role ABCs (D4, D5)

### The catalog's ports

`CatalogRepository` (10 operations) and `DownloadCatalogReader` (3, declared in `application/`) become:

| Port | Operations |
|---|---|
| `ObservationWriter` | `record_observation` |
| `ObservationReader` | `read_latest_observation`, `read_best_observation`, `read_known_filenames` |
| `DecisionWriter` | `record_decision`, `record_retraction` |
| `DecisionReader` | `read_latest_decisions`, `read_download_candidates` |
| `CatalogScanner` | `read_file_count`, `iter_latest_observations` |

`SqliteCatalogRepository` inherits all five. Why: each operation declared once (D5), a consumer depends on the
ports it calls; `download_candidates` reads decisions (the latest verdict of tier download), so the decisions'
reader holds it, at the cost of one unused method in two fakes.

### local.db's ports

| Today | Becomes |
|---|---|
| `DownloadRepository` (in `application/run_download_cycle.py`) | `DownloadWriter` (`record_queued`, `record_completed`, `set_state`, `mark_seen`), `DownloadReader` (`is_tracked`, `read_last_seen_at_by_file`, `read_tracked_states`, `read_queued_target_id`), in `ports/driven/` |
| `SourceRepository` | `SourcePointWriter` (`record_readings`), `SourcePointReader` (`read_earlier_points`, `has_points_before`) |
| `BackoffStateRepository` | `BackoffStateReader` (`read_backoff_states`), `BackoffStateWriter` (`save_backoff_states`) |
| `LocalStateRepository` | `NodeIdReader`, `NodeIdWriter` (above), `PolicyFingerprintReader` (`read_policy_fingerprint`), `PolicyFingerprintWriter` (`set_policy_fingerprint`) |

### The other ports

Named after who acts, as lot 1a's spec promised:

| Today | Port | Adapter |
|---|---|---|
| `DiskSpace` (`free_bytes`) | `FreeSpaceMeter` | `ShutilFreeSpaceMeter` |
| `Rng` (`jitter`) | `JitterGenerator` | `RandomJitterGenerator` |
| `Telemetry` (`emit`) | `EventEmitter` | the dispatcher, unchanged |
| `MetricsSink` (`apply`) | `MetricsRecorder` | `PrometheusMetricsRecorder` |
| `WakeHub` (`wake`, `wait`) | `Waker` | `AsyncioWaker` |

`Notifier`, both clocks, the four `*Client` ports, `CatalogCopier`, `CatalogFinder` and `ConfigChecker` keep their
names.

### The conversion

- Every port left a `Protocol` becomes an ABC its implementers and fakes inherit, `Matcher` and its seven
  implementers in `catalog_matching` included.
- `SearchClient.channels`, the one attribute in a port, becomes a method.
- `@runtime_checkable` goes from the three telemetry ports, with the `isinstance` test that relies on it.
- `LoopCrawlerControl`'s `__slots__` and the test that reads them go (the Serena spec's decision): they stop
  locking once the class inherits a slotless port.
- The five download doubles `test_run_download_cycle_loop.py` imports from `test_run_download_cycle.py` move to
  `p2pwatch_testing` before any port they implement is renamed, which closes pyrefly's `tests.*` gap for those
  renames.
- An ast-grep rule refuses a `Protocol` base under `packages/crawler/src`, `packages/matching/src` and
  `packages/crawler_testing/src` (D17), with its rule test.

## `AGENTS.md` and the strings no tool sees

Each block rewrites by hand, and lists in its pull request: logger names, `tach.toml`'s modules, the vulture
whitelist, `tests_without_unit` keys, module paths and class names in `docs/contributing/architecture.md`
(`WakeHub`, `FileObservation`, `PrometheusSink` among them) and in `AGENTS.md`. Logger names that change (the lines
moving from the composition to `RunCrawler`) go in `docs/migration-4x.md`.

`AGENTS.md` changes in the block that makes it false (D19):

| Block | What becomes false or new |
|---|---|
| 10 | the `Writer`/`Reader` and capability conventions, the `Logger` port; "`logging` stays in `application/`'s list until lot 2 gives it a port" |
| 50 | the glossary: `reported file`, `observation` |
| 80 | the use case rule's root exception (`RunCrawler`) |
| 85 | the glossary: `run state` |
| 100 | the invariant on the adapters holding a `MonotonicClock` (the board no longer does) |
| 110 to 170 | the webui row of "Where the code lives"; the glossary: the new domain concepts, `display`, the response models |
| 190 | `PrometheusSink` in the boundary discipline invariant; the glossary's `wake` line (`Waker`); the Gotchas that assume `Protocol` ports: the one-line stub idiom becomes the `@abstractmethod` one, the Serena rename "from the port, then from each implementer" |

## Blocks

Sizes are estimates from the measurement, not a dry run: each teammate measures its block and splits it at a
bound. New ports are born ABCs, so the conversion converts only what is left.

| # | Branch | Holds | Lines, files (est.) |
|---|---|---|---|
| 10 | `feat/logger-port` | this spec, the corrections, the backlog; `Logger`, `StdlibLogger`, `FakeLogger`; the seven modules on it; `logging` off the allowlist | 600, 23 |
| 20 | `test/download-doubles-shared` | the five download doubles into `p2pwatch_testing` | 200, 4 |
| 30 | `refactor/amuleapi-session` | `_call` opens the session; closed stays closed; the re-login serialized | 111, 7 |
| 35 | `refactor/one-amuleapi-session` | `connect`/`close` off the ports; one session per node (Corrected 2026-10-19: split from block 30, measured at 24 files; this half moves behaviour, so no exemption) | 265, 19 |
| 40 | `refactor/reported-file` | `FileObservation` renamed `ReportedFile`, with its variables | 200, 19 |
| 50 | `refactor/one-observation` | `FileObservation` with `observed_at`, born with the write | 179, 14 |
| 55 | `refactor/observation-reads` | every read returns `FileObservation` whole; `Sighting`, `ObservedFile`, `ReevalRow` deleted (Corrected 2026-10-19: split from block 50, measured at about 32 files; it moves behaviour, so no exemption) | 300, 18 |
| 60 | `refactor/node-id-catalog-and-source-points` | the `node_id` through the catalog's three writes and the source points' write and two reads | 550, 22 |
| 70 | `refactor/node-id-notifications` | the `node_id` through `emit` and `notify`; Apprise's groups per `node_id` | 400, 16 |
| 75 | `refactor/node-id-ports` | `NodeIdReader`, `NodeIdWriter`, `NodeIdGenerator`; `resolve_node_id` on them (Corrected 2026-10-19: split from block 80, measured at 507 lines; it moves behaviour, so no exemption) | 235, 13 |
| 80 | `feat/run-crawler` | `RunCrawler`; the loops launched with the `node_id`; the composition only builds | 285, 8 |
| 85 | `refactor/asyncio-run-state` | `RunStateWriter`, `RunStateReader`; `AsyncioRunState` inheriting both (Corrected 2026-10-19: split from block 90, counted at 21 files before any code; it moves behaviour, so no exemption) | 150, 7 |
| 90 | `feat/crawler-control-use-cases` | `PauseCrawl`, `ResumeCrawl`, `RequestShutdown`; the webui and `PosixProcess` on them; `CrawlerControl` deleted | 330, 15 |
| 100 | `refactor/in-memory-status-board` | `InMemoryStatusBoard` and its two ports; the freshness rule into the domain | 300, 10 |
| 110 | `feat/describe-node` | `NodeState`, `TrackedDownload`, the backoff types into the domain; `NodeStateReader`; `DescribeNode`, `/node` on it (Corrected 2026-10-19: block 110 split in 110, 115 and 117, counted at about 25 files before any code; it moves behaviour, so no exemption) | 400, 17 |
| 115 | `feat/crawl-summary` | `TargetCoverage`, `CoverageReader`; `SummarizeCrawl`, `/` on it; the dashboard's deprecated edges removed | 450, 16 |
| 117 | `test/crawl-summary-routes-on-fakes` | the `/` and `/node` route tests on fakes of `CrawlSummarizer` and `NodeDescriber` | 400, 5 |
| 120 | `refactor/catalog-file-counts` | `CatalogFileReader` with its two counts; `/files` reads them under the existing deprecated edge (Corrected 2026-10-19: block 120 split in 120, 123 and 125, measured at 877 lines; it moves behaviour, so no exemption) | 187, 6 |
| 123 | `refactor/catalog-entry` | `CatalogEntry` in the domain; `read_catalog_entries`; `FileRow`, `FileDecision`, `_ISO` deleted | 498, 10 |
| 125 | `feat/list-files` | `ListFiles` behind `FileLister`, the files and target routes on it (Corrected 2026-10-19: `FileListing` holds `CatalogEntry`s, no `ListedFile`, which would wrap one with nothing added) | 280, 9 |
| 130 | `test/list-files-routes-on-fakes` | `FakeFileLister`; the files and target routes' decoding tests on it (Corrected 2026-10-19: split from 135, measured at 605 lines; it moves assertions, so no exemption) | 354, 4 |
| 135 | `test/files-rendering-on-fakes` | the files table's rendering tests on the fake; the fixtures no test needs deleted | 255, 1 |
| 140 | `refactor/sharing-period` | `PeriodWindow` and `SharingPeriod` in the domain, `SourcePeriodView` replaced; `SourceReader.read_sharing_periods` (Corrected 2026-10-19: block 140 split in 140, 143, 145 and 147, counted at 21 files and about 1,400 lines before any code; it moves behaviour, so no exemption) | 350, 8 |
| 143 | `refactor/file-history` | `FileHistory`, `DatedDecision` in the domain; `CatalogFileReader.read_file_history`; `FileDetail`, `DecisionView` deleted | 300, 8 |
| 145 | `refactor/domain-interval` | `interval.py` to `domain/` (Corrected 2026-10-19: split from 146, measured at 676 lines, the move counted twice; it moves behaviour, so no exemption) | 283, 8 |
| 146 | `feat/describe-file` | `DescribeFile` behind `FileDescriber`; its route on it | 393, 8 |
| 147 | `test/describe-file-routes-on-fakes` | `FakeFileDescriber`; the file page's decoding tests on it (Corrected 2026-10-19: block 147 split in 147, 148 and 149, measured at 875 lines; it moves assertions, so no exemption) | 138, 3 |
| 148 | `test/file-page-rendering-on-fakes` | the file page's general, decision and explanation rendering on the fake | 457, 1 |
| 149 | `test/file-page-history-on-fakes` | the file page's timeline, source history and interval selector on the fake | 294, 3 |
| 150 | `feat/list-sources` | `SourceReader`'s list reads; `ListSources`; its route and route tests | 450, 12 |
| 160 | `feat/describe-source` | `SourceHistory`; `read_source_history`; `DescribeSource`, `/sources/{id}` on it; the dead `{% else %}` (Corrected 2026-10-19: block 160 split in 160, 163 and 165, counted at 19 files and about 1,100 lines before any code; it moves behaviour, so no exemption) | 400, 14 |
| 163 | `refactor/source-name-history` | `SourceNameHistory`; `read_source_name_history`; `CatalogReader` and the views it returned deleted (Corrected 2026-10-20: split from 164, measured at 517 lines and 20 files; it moves behaviour, so no exemption) | 245, 14 |
| 164 | `feat/describe-source-name` | `DescribeSourceName`, `/sources/name` on it; the webui's deprecated edges to the readers | 280, 9 |
| 165 | `test/source-pages-routes-on-fakes` | the two source pages' route tests on fakes of their describers | 350, 5 |
| 170 | `feat/console-query` | `SqlExecutor`, `RunConsoleQuery` behind `ConsoleQueryRunner`; the console's routes on it (Corrected 2026-10-20: block 170 split in 170, 173 and 175, counted at about 870 lines and 25 files before any code; it moves behaviour, so no exemption) | 470, 16 |
| 173 | `test/console-routes-on-fakes` | the console's route tests on a fake `ConsoleQueryRunner`; the last fixture databases leave the route tests | 350, 5 |
| 175 | `refactor/webui-displays` | `views.py` becomes `displays.py`, every view model a `<Thing>Display`; the last webui exceptions in `tach.toml`; Acceptance 7 to 9 | 150, 9 |
| 180 | `refactor/role-ports` | the five catalog ports, `CatalogRepository` and `DownloadCatalogReader` deleted; the download, source point, backoff and policy fingerprint ports; the re-exports of the types blocks 110 and 115 moved to the domain (`BackoffKey`, `BackoffState`, `StatusReading`, `ClientStatus`, `ChannelStatus`) go, their importers reading the domain (Corrected 2026-10-19: added) | 900, 34 |
| 185 | `refactor/read-types-in-domain` | `DownloadCandidate`, `RecordedReading`, `EarlierPoints` and any other type a driven read port still owns move to the domain (Corrected 2026-10-20: added, block 180 found them left against the convention) | |
| 190 | `refactor/ports-as-abcs` | the five capability renames; the remaining `Protocol`s to ABCs; `channels`; the Gotchas; the ast-grep rule and its test | 750, 72 |
| 200 | `fix/holistic-code-and-tests` | the holistic review's code and test findings (Corrected 2026-10-20: the closing block split in 200, 203 and 210 after the holistic review's 39 findings) | |
| 203 | `refactor/holistic-names` | the holistic review's naming and docstring findings | |
| 210 | `docs/hexagon-p2pwatch-wrap` | closing block: the docs findings, backlog, handoff | |

- Blocks 10, 60, 180 and 190 pass a bound: each only replaces names, signatures or base classes, with no behaviour
  moved (the injected logger for the module global, a parameter threaded to its call sites, a port split into its
  roles, a `Protocol` base for an ABC), so they take the size exemption. (Corrected 2026-10-19: block 20 takes
  it too, measured at 540 lines: a move counts its lines once deleted and once added, and moves no behaviour.)
  (Corrected 2026-10-19: block 40 takes it too, measured at 23 files and 270 lines: a pure rename.)
  (Corrected 2026-10-19: block 70 takes it too, measured at 20 files and 227 lines: the `node_id`
  threaded to the call sites of `emit` and `notify`.)
  (Corrected 2026-10-20: block 185 takes it too, measured at 45 files and 427 lines: types moved with their imports.)
- 19 blocks before the closing one, more than the 12 to 15 Discuss first estimated: `RunCrawler`, the `node_id`
  through the calls, the route tests on fakes and the local.db splits each added some. Lot 1b's 17 blocks went with
  no fix-back and no cascaded rebase.
- The webui's deprecated edges in `tach.toml` go page by page, the last in block 175 (Corrected 2026-10-20: was 170); `exact` fails a block that
  leaves an unused one.

## Acceptance

1. **No `Protocol` in the hexagon** (block 190): `grep -rnE "^class \w+\(.*\bProtocol\b" packages/crawler/src
   packages/matching/src packages/crawler_testing/src` prints nothing (on `main`: 21 lines), and the ast-grep rule
   is seen failing on an injected `class X(Protocol)`.
2. **No `logging` in the core** (block 10): ast-grep fails on an injected `import logging` in `application/`;
   `grep -rln "import logging" application` prints nothing (on `main`: 7 files).
3. **No `connect` on a port, one session** (blocks 30 and 35; Corrected 2026-10-19: was block 30): `grep -rn "def connect\|def close" ports` prints nothing; the
   wiring test with download enabled asserts one `POST /auth/login` on `FakeAmuleApiServer` (on `main` it asserts
   `api.logins == 2`, `test_app_wiring.py:196`); a client test sees a call after a tolerated unreachable `open()`
   log in and succeed, and a call after `close()` raise.
4. **The composition runs nothing** (block 80): for each pattern of `resolve_node_id($$$)`,
   `reevaluate_if_policy_changed($$$)`, `supervise_loops($$$)` and `$X.emit($$$)`,
   `uv run ast-grep run --lang python -p '<pattern>' packages/crawler/src/p2pwatch/composition/app.py` prints
   nothing (at block 75's tip: one call each). (Corrected 2026-10-19: was a `grep` on the names, which also
   matched the logger name the composition hands `RunCrawler`; the check is on the calls.)
5. **No `node_id` in an adapter's state** (block 70): `grep -rn "self\._node_id" adapters` prints nothing but
   `AppriseNotifier`'s groups keyed by it (on `main`: 13 lines in the three adapters).
6. **Each operation declared once** (block 190): the appendix's ast-grep command prints only `now` (on `main`:
   `best_observation`, `close`, `connect`, `download_candidates`, `latest_observation`, `now`). `now` stays twice by
   design: `WallClock.now` and `MonotonicClock.now` are two operations (D5). (Corrected 2026-10-19: was an `awk`
   on the text of the classes; the ast-grep rule reads the syntax tree, and prints the same list on `main`.)
7. **No exception left for lot 2** (block 175; Corrected 2026-10-20: was 170): `uv run tach check 2>&1 | grep -c '^\[WARN\] packages/crawler/'`
   prints 0 (on `main`: 66), and `tach.toml` names lot 2 nowhere.
8. **The route tests use fakes** (block 175; Corrected 2026-10-20: was 170):
   `grep -lE "sqlite3|catalog_db|local_db|catalog_rows|insert_file|close_test_connections" tests/adapters/driving/webui/test_app*.py`
   prints nothing (on `main`: both files).
9. **The pages render as before** (block 175; Corrected 2026-10-20: was 170): a throwaway script renders, from the same fixture databases, a
   fixed wall clock, a fixed status reading and the crawler running, on `main` and at the top of the stack:
   every read page at its default URL, `/files` sorted by one column, filtered on one tier and on page 2,
   `/targets/{id}`, one file and one source on a preset interval, `/sources/name?...`, and one console query;
   `diff` of the two outputs prints nothing. The script and its output go in block 175's report.
10. **Nothing out of scope changes**: `git diff -M100% --name-status origin/main...<top branch> -- '*/migrations/*' deploy/ | grep -v '^R100'`
    prints nothing; the `Route(` lines of the webui's module are the same set; the diff of `adapters/driven/config/`
    and of the Prometheus adapter shows no key or metric name changed; the notifier's tests assert the Discord
    username `p2pwatch - <node_id>` and the prefixed title.
11. **The gate is green** at every block, and CI's smoke and integration suites pass on amd64 and arm64 at blocks
    35, 80 and 175 (Corrected 2026-10-19: 35 for 30, the split's top; 2026-10-20: 175 for 170).

## Risks

- **The node's identity in every write** is a wide signature change: a write given the wrong `node_id` would
  attribute observations to another node. The wiring tests assert the `node_id` stored on a written row.
- **Rewriting the route tests** can lose an assertion: each rewrite block lists every old assertion and where it
  went.
- **Two loops share one session**: a hung request no longer blocks the download loop alone. The 10-second
  `timeout_seconds` of the client bounds it, as today for the search and status loops.

## Backlog

- **Hexagonal architecture**: the lot 2 sub-item is deleted at Wrap; lot 3 stays.
- **A copy before a migration that rewrites rows** stays open and must ship before the next release; this lot
  changes the image, so it is not released before that.
- **Contract tests for the fakes** stays open: it waited for the ports' final shape, which this lot gives, so it
  can follow.
- **Test quality** and **Mutation testing in the gate** stay open, after this lot, as the umbrella says.
- **The logic-free template guard on Jinja's syntax tree** stays open: this lot moves no template logic.
- **Sort the files view by first seen** and **The webui in the visitor's time zone** stay open, better after this
  lot, which rewrites the read side they touch.
- **Every stamp an integer of microseconds**, **Adopt ty** and **Multi network, stage 5** stay open: none
  concerns this lot's ports.

## Corrections of earlier specs

Marked `(Corrected 2026-10-19: ...)` by block 10:

- Umbrella, Measurements: 21 `Protocol`s in the hexagon (not 26 in all), 31 `_logger` calls in 7 modules (not 27 in
  5), the composition seams already gone (lot 1a).
- Umbrella D6: the status board and the run state are driven ports a use case consumes, not driving ports.
- Umbrella D7: the loops and the startup steps are internal steps of `RunCrawler`, which is the graph's root and has
  no driving port.
- Umbrella D8: a read projection is a domain concept the read port returns, not a type the driven port owns; the
  response models stay with their driving port.
- Umbrella D10: half of it already in the tree; one session per node.
- Descriptive names, section 7: two observation types (`ReportedFile`, `FileObservation`), not one; no `Record` types
  and no `records.py`: a read port returns domain types, and the missing concepts join the domain; the webui's
  read-only connection already exists.
- Serena spec, "For the architecture lot": `WebuiServer` and the intersection types are gone; the `__slots__` test
  reads the tuple, no `vars()`.
- Lot 1a's spec, "Names": `CrawlerControl` and `StatusReadings` are deleted rather than renamed.

## Appendix: measurements

Taken on `main` at `859b440` on 2026-10-19 (`.reviews/lot2-measure.md`, recounted by `.reviews/lot2-spec.md`).
Re-run before acting on one.

- `Protocol`s: `grep -rnE "^class \w+\(.*\bProtocol\b" packages/crawler/src packages/matching/src packages/crawler_testing/src`:
  21, 18 under `ports/` in 15 files, `DownloadRepository` and `DownloadCatalogReader` in
  `application/run_download_cycle.py`, `Matcher` in `catalog_matching/domain/combinators.py` (7 implementers).
  6 ports are already ABCs.
- Logging: 31 `_logger` calls in 7 `application/` modules (18 in `run_download_cycle`), `info`, `warning` and
  `error` only; 6 test files read them with `caplog`.
- `connect`: called in `search_worker.py:166`, `status_loop.py:113`, `run_download_cycle.py:483`; `close` on no
  port; `_call` raises when `_http is None` (`adapters/driven/mule_api/client.py:286-287`); a second client at
  `composition/app.py:269`.
- Operations declared twice, run from `packages/crawler/src/p2pwatch` (the methods of every class whose bases name
  `Protocol` or `ABC`):
  `uv run ast-grep scan --json=stream --inline-rules '{id: op, language: python, rule: {kind: function_definition, has: {field: name, pattern: $NAME}, inside: {kind: class_definition, stopBy: end, has: {field: superclasses, regex: "\\b(Protocol|ABC)\\b"}}}}' ports application | python3 -c "import json,sys; [print(json.loads(l)['metaVariables']['single']['NAME']['text']) for l in sys.stdin]" | sort | uniq -d`
  prints `best_observation`, `close`, `connect`, `download_candidates`, `latest_observation`, `now`.
- Webui: `webui/app.py` 1,147 lines, 15 routes, readers built per request at 9 sites; `views.py` 524 lines, 39
  classes, 13 of them the readers' types; `catalog_read.py` 726 lines; 12 `deprecated = true` edges naming lot 2
  (`tach.toml:185-255`, 8 comments); `test_app.py` 2,663 lines, 114 tests.
- `node_id` in adapters: `SqliteCatalogRepository` (observations and decisions), `SqliteSourceRepository`
  (a write and two reads), `AppriseNotifier` (`app_id`, title prefix); `.emit(`: 15 sites, 14 in 5 `application/`
  modules and 1 in the composition.
- `raw_meta`'s decode, on the deployed node's catalog (read-only, `mode=ro`, the pre-variants schema of the running
  release, 2,127 files), one `raw_meta` per file: 2.05 s without `json.loads`, 2.16 s with it, after a cold first
  pass of 10.4 s. Measured on the host, not in the hardened container: the decode is CPU, not temp space.
