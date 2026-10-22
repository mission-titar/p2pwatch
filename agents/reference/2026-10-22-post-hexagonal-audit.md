# Post-hexagonal audit: the inconsistencies left after the umbrella, and their arbitration

- Tree: `main` at `1d677b82` (lot 3c merged), 2026-10-21. Read only; no repository file changed.
- Mapped by four Opus agents (the crawler hexagon's architecture, naming across the eight packages, the five other
  hexagons, the guidance and docs against the tree) and one Sonnet agent (the hexagonal literature). Only Cockburn's
  article was fetched; the other sources in section L are the agent's reading of them, not fetched quotes.
- Structural rules hold: `grep -c "deprecated = true" tach.toml` is 0, no adapter imports another, no `Protocol` and
  no `monkeypatch` is left, every module is declared in `tach.toml`.
- Verified: **L** re-checked by the lead in this session, **V** checked in code by an agent, **P** plausible, to
  re-check before it is arbitrated.
- Discipline for the Discuss: facts and the lead's view are kept apart (the "Lead's view" lines only); an item is
  closed only by the operator's decision, recorded in the ledger with its exit (`agents/workflow.md`, "Review
  findings": fixed in a lot, a `BACKLOG.md` entry after agreement, an accepted limit written where the decision
  lives, or refused with its reason). The rules (R) come first, since several findings depend on them. Before
  arbitrating an item, re-run its evidence: a line number may have moved.
- The operator's order for any fix (2026-10-22): enforced by design first, else by tests, else by a gate tool, and
  only when nothing enforces it automatically, by a convention. Each option states its level.

## Ledger

| ID | Item | Verified | Depends on | Decision | Exit |
|---|---|---|---|---|---|
| R1 | The composition implements a driving port | L | | a, 2026-10-22: kept, stated as a rule | fixed in a lot: `AGENTS.md`'s sentence, `RunPortSyncLoop.run_port_sync_loop` renamed `run` |
| R2 | Where read models live | L | | already decided by lot 2's spec, no question | A11 narrowed to `PAGE_SIZE` |
| R3 | An adapter implementing a Writer and a Reader; "Repository" | L | | d, 2026-10-22: `<System><Thing>Store`; "store" in the glossary; Naming's adapter rule reworded "the system, the thing and the role"; `RepositoryError` to `StoreError` | fixed in a lot; names arbitrated one by one (N2, N5, N9) |
| R4 | The status of `application/` modules that are not use cases | L | | a, 2026-10-22: `application/` holds the use cases (called from outside, through a driving port) and the steps (called only from inside, by a graph's root), which call ports; what calls no port goes to `domain/`; the two kinds kept apart in `application/` | fixed in a lot: A7, H1, D6; the layout in R14 |
| R14 | How `application/` keeps use cases and steps apart | | R4, R12 | 2026-10-22 (corrected in the Discuss from `use_cases/` + `crawl/`): `application/ports/{driving,driven}/`, `application/use_cases/` (called from outside, through a driving port), `application/steps/` (called only from inside), and at `application/`'s root at most one `<x>_lifecycle.py`, the program from its start to its stop, which the composition runs: `RunCrawler` becomes `CrawlerLifecycle`, `RunPortSyncLoop` `PortSyncLifecycle` ("lifecycle" in the glossary). tach: the lifecycle may import `steps/`, `use_cases/` may not, `steps/` imports neither | fixed in a lot |
| R5 | A Reader over an outside system | L | | b, 2026-10-22: `Reader` and `Writer` only over our own state (databases, files, memory); an outside system keeps a capability name (`StatusClient`, `SourceClient` stay) | fixed in a lot: `RepoReader`, `ForwardedPortReader` renamed, names arbitrated one by one |
| R6 | The scope of "a check returns a report" | L | | a, 2026-10-22: `validate-config` is a check; `ValidateConfig` catches the parser's `InvalidConfigError` and returns a `ConfigReport`; the parser still raises for the crawl. Accepted limit: one problem, the parser stopping at the first | fixed in a lot; the limit written in that lot's spec. Open still: R6b, R6c |
| R6b | The type of `problems`, and the ring that formats them | V | R6 | a, 2026-10-22: a problem is a typed value, formatted by the command line | fixed in a lot: `coverage_checks`, `template_checks` |
| R6c | Observability's `Report`, another meaning of the word | L | R6 | a, 2026-10-22: `EventDescription`, from `describe`; superseded in A3 by `ObservabilityPlan` | fixed in a lot |
| R7 | A Writer that returns a value | L | A2 | a, 2026-10-22: a Writer returns nothing; `record_queued` preceded by `is_tracked` (one writer on the event loop, no `await` between); the roles decided outside the store (A2) | fixed in a lot |
| R8 | Logger names that are no module | L | | c, 2026-10-22: the name derived from the code, `StdlibLogger(<Class>.__module__)` in the composition, `logging.getLogger(__name__)` in an adapter; drift impossible by design | fixed in a lot; `migration-4x.md` updated |
| R9 | One port per file, tach's granularity | L | | a, 2026-10-22: one port per file, named after it; tach then holds each adapter to exactly the ports it uses (gate) | fixed in a lot: the 12 files split |
| R10 | A port file's name | V | R9 | settled by R9: the port's name in snake case, checked by a test | fixed in a lot |
| R11 | Where command-line defaults and repository paths live | L | | a, 2026-10-22: a value the operator could set and did not (a key, an env var, an option) is the domain's; a fixed value no option sets is a constant of the composition (D13) (Corrected 2026-10-22 by lot A's spec, D8: from "of `__main__`", written when `__main__` was the composition root; `__main__` now only reads the process state, as H6 says); an ast-grep rule refuses a literal `default=` | fixed in a lot: the crawler's three options, `amule_bump`'s two, vex's `--format` |
| R12 | Divergences from the literature to confirm or reopen | | | 2026-10-22: 2, 4, 5 confirmed; 3 reopened, the ports move into `application/` as the common usage has it (Hombergs, Graça, Martin's boundaries), for familiarity; 1 confirmed after discussion (one driving port per use case, for testability and tach's mechanical check; Cockburn's ports by actor and CQRS reads weighed) | 3: fixed in a lot, the layout arbitrated with R14's |
| R13 | `CrawlerApp` and `PortSyncApp` named as the application | L | R1 | a, 2026-10-22: `CrawlerComposition`, `PortSyncComposition` (what is theirs is the assembly; the ring's word) | fixed in a lot |
| R15 | Composition in two places, `__main__.py` and `composition/` | L | R13 | b, 2026-10-22: every hexagon's whole composition in `composition/` (the four tools gain the ring); `__main__.py` only reads argv, env and cwd and calls it; tach refuses any other import of `__main__` | fixed in a lot; likely settles H2 and H14 |
| A1 | The run state read through raw `asyncio.Event`s | L | | a, 2026-10-22: `RunStateReader` gains the waits on the resume and the shutdown (as `Waker.wait`); the loops receive the port only, no `Event` in their signatures (by design) | fixed in a lot |
| A2 | Source point rules in the SQLite store | L | R7 | 2026-10-22: the step reads the previous point's role through `SourcePointReader`, decides with the domain's `carried_role`, and has the store write the points with their roles; dropping a reading with neither source nor name and refusing an invalid contact point leave the store too; the time between reads computed by the domain | fixed in a lot |
| A3 | Event dispatch orchestrated by a driven adapter | L | | a, 2026-10-22: the dispatch becomes an application step; `MetricsRecorder` and `Notifier` become ports the core calls. `describe` renamed `plan_observability`, returning an `ObservabilityPlan` (replaces R6c's `EventDescription`) | fixed in a lot |
| A4 | Notification formatting in the domain | L | R6b | a, 2026-10-22: the domain produces a typed notification (its kind, targets, file, link, source), the apprise adapter writes the Markdown (by design: the plan carries no notification text); log lines stay plain text written in the domain | fixed in a lot |
| A5 | `CoverageReader` returns primitives | L | A8 | 2026-10-22, with A8: returns `DecisionTier`s | fixed in a lot |
| A6 | The composition runs a startup step | L | | 2026-10-22: `CrawlerLifecycle` resumes the persisted backoff waits at its start, beside the node id and the policy check | fixed in a lot |
| A7 | Pure rules in `application/` | V | R4 | settled by R4: they go to `domain/` | fixed in a lot |
| A8 | Tier rules scattered and stringly typed | L | | 2026-10-22: a `DecisionTier` type in the matching domain carries its order and the "catalog identifies no target" rule; the webui and the ports use it (by design); the coverage status typed the same way. The word "tier" kept (the operator's, in `matcher.yml`, the metrics, the docs) | fixed in a lot |
| A9 | The client and config error contracts | L | R3 | 2026-10-22: each amuleapi method raises its operation's port error (search, download refused, a new read refused); `ApiRejectedError` internal to the adapter, inheriting no port error; a test per method. The config half needs no change: `ConfigError` is internal to the config adapter and translated into `InvalidConfigError` at its port (the same pattern), which lives in `domain/` as a type both sides use (lot 2's rule) | fixed in a lot (client half) |
| A10 | Merge's same-catalog rule in two adapters | L | | 2026-10-22: `MergeCatalogs` compares the paths the finder resolved and hands the copier only the sources to copy; no `destination_is_source` flag (by design) | fixed in a lot |
| A11 | `PAGE_SIZE` in `domain/`, read by `application/` only | L | R2 | settled by intent: moves to `application/` | fixed in a lot |
| A12 | `PosixProcess` owns the resource stack | L | | 2026-10-22: the composition keeps its own resource stack; `PosixProcess` only installs and removes its signal handlers, nested so the resources close before the handlers go (a second Ctrl-C still forces the exit) | fixed in a lot |
| A13 | Config parsing placed two ways | L | R4 | 2026-10-22: as the matching: the adapter reads `crawler.yml` and resolves `${NAME}`, the domain checks the mapping and builds the config; `AMULE_CLIENT_NAME` among the domain's values | fixed in a lot |
| A14 | `DOWNLOAD_WAKE_SUBJECT` shared between two loops | L | | 2026-10-22: a `WakeSubject` type in the domain (`DOWNLOAD`), the only type `Waker` takes (by design) | fixed in a lot |
| A15 | `MatchingExplainer` builds its own engine | L | R4 | 2026-10-22: moves to `domain/` (it calls no port) and receives the engine the composition builds | fixed in a lot |
| A16 | `p2pwatch_testing`'s layout | V | R9 | superseded by H8: the package folds into the crawler's `tests/`. Was, 2026-10-22: mirrors `src`: a port's fake at the mirror of its port's file, one per file; the SQLite helpers under `adapters/driven/persistence_sqlite/`; a test checks each fake's path | fixed in a lot |
| A17 | `node_id` passed on every driven call | L | A4 | 2026-10-22 (lot 2's alternatives re-read: constructor, factory, context provider stay refused): a domain object carries who produced it and when, written as read: the observation carries its node, a decision or retraction is written as a `DatedDecision`, the typed notification (A4) and the events carry theirs; `node_id` stays a parameter only as a read's filter; Writers take the object only (by design) | fixed in a lot |
| H1 | `amule_bump`'s pure logic in `application/` | V | R4 | settled by R4: to `domain/` | fixed in a lot |
| H2 | Boot and port-sync read the environment in two rings | V | R15 | settled by R15: the composition parses boot's environment as port-sync's; the driving port carries no `env` | fixed in a lot |
| H3 | `vex_checks` derives its root from `__file__` in `main` | L | | 2026-10-22: the root is `cwd`, which `__main__` reads and passes; CI and poe run it from the repository's root | fixed in a lot |
| H4 | `vex_checks`' placeholder location overwritten | L | R6b | 2026-10-22: the domain returns the contradicted premise with no location; the use case builds the located problem (by design: no location field in the domain's type) | fixed in a lot |
| H5 | `vex_checks`' bijection in the use case | V | R4 | settled by R4: to `domain/`, the use case reading through its ports | fixed in a lot |
| H6 | Adapters hard-coding their tunables | V | R11, R15 | settled by R11: a fixed value no option sets is a constant of the composition, passed to the adapter | fixed in a lot |
| H7 | Two ways to run a command | L | | 2026-10-22: every adapter that runs a program receives `run_command`, one type; the grype adapter tested whole; `AGENTS.md` keeps one form of "an adapter receives what it drives" for commands | fixed in a lot (with H12) |
| H8 | Driving-port fakes in two places | L | A16 | 2026-10-22: one convention for every hexagon: a port's fake at the mirror of its port's file under the package's `tests/fakes/`; `p2pwatch_testing` folds into the crawler's `tests/` (supersedes A16's location). Trial b held (scratch clone at `1d677b82`): each package's `[tool.pyrefly]` with `python-interpreter-path = "../../.venv/bin/python"` and `search-path = ["src", "."]` (this order: `"."` alone collapses the rename to 1 site) resolves every `tests.*` import, and a rename from the port reaches a fake's override in `tests/` (`RepoReader.read_file` 12/12 against 9, `VexReader.read_claims` 11/11 against 8, 3 fresh servers each); mypy green, src renames unchanged. The copy per package is required (pyrefly's sub-configs cannot change import paths); `pyrefly check` limited to import errors joins the gate so a forgotten section fails (amule_bump's `missing-attribute` at `test_bump_amule.py:97` fixed first) | fixed in a lot |
| H9 | pytest settings differ between packages | L | | 2026-10-22 (a workspace test and poe's `PYTEST_ADDOPTS` weighed and refused): a pytest plugin, a dev tooling package installed by the root's `dev` group and auto-loaded through its `pytest11` entry point, applies `--strict-markers` and the resource-warning filters to every run, the gate's and a hand-run `pytest` alike; the packages' own lines go. Acceptance: a hand-run `pytest` in each package refuses a misspelled marker. Its structure under R12's "a full hexagon per tooling package" to settle in the lot | fixed in a lot |
| H10 | An unparsable template: raised by one check, reported by the other | L | R6 | 2026-10-22: one rule for every tool: a broken input raises, the command line prints it and exits in error; a problem is a finding on a valid input; `logic-free` aligns | fixed in a lot |
| H11 | `cwd` typed two ways; `.resolve()` in a driving adapter | L | | 2026-10-22: `PurePath` in every command line (by design: no `.resolve()`); a path resolved on disk by the driven adapter that reads it; `_under_cwd`'s four copies accepted (hexagons never import one another) | fixed in a lot |
| H12 | `parse_grype_json` public and tested directly | L | H7 | settled by H7: private, tested through `scan_sbom` | fixed in a lot |
| H13 | `Pin.arg_lines` duplicates the `ARG` format | L | | 2026-10-22: one function makes an `ARG` line, used by the rewrite and the dry-run print | fixed in a lot |
| H14 | `p2pwatch_amule`'s duplicated wiring | V | R15, R8 | settled by R15 (one composition builds each adapter once) and R8 (the logger named from its module) | fixed in a lot |
| H15 | The application raises a `FileNotFoundError` itself | L | | a, 2026-10-22: an explicit branch for a missing `amule.conf` (its own log line, amuled left as is), at the first read and at the re-read after the stop; a real `OSError` still caught; same behaviour | fixed in a lot |
| N1 | Clock adapter files named against their class | L | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N2 | `persistence_sqlite/`'s three file schemes | V | R3 | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N3 | amuleapi spelled three ways | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N4 | `Posix`, `Filesystem` and `Json` prefixes | P | | 2026-10-22: the system is what would need another adapter if replaced: a service or a database (`AmuleApi`, `GitHub`, `Sqlite`, `S6`), a format's producer (`Syft`, `CoveragePy`, `OpenVex`), the OS (`Posix`) beyond reading and writing a file (accounts, ownership, signals), else `Filesystem`; never a syntax (`Json`, `Yaml`) | fixed in a lot: `JsonVexReader`, `JsonSarifWriter`, `YamlConfigChecker` renamed, names arbitrated |
| N5 | "Source" for two concepts in adapter names | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N6 | The status board's ports named after `ClientStatus` | V | R10 | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N7 | Display names with the glossary's "Never" words | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N8 | `Download*` ports and "local state" against the glossary | P | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N9 | Fakes named after no port | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N10 | Doubles without the `Fake` prefix | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N11 | `last` for the most recent | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N12 | Abbreviations outside the glossary | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N13 | `ed2k_hash` past the mapper | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N14 | Generic local names | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N15 | Stale words in prose ("layer", "EC", ...) | V | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N16 | `CrawlerRunner.crawl`, `ConsoleQueryOutcome` | V | R1 | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| N17 | Writers' verbs for one act | P | | 2026-10-22: `record_*` adds a fact and leaves the earlier ones (observations, decisions, source points, the node id written once); `set_*` replaces a current value; an ast-grep rule refuses a Writer method starting otherwise | fixed in a lot: `save_backoff_states`, `mark_seen`, `publish` renamed, names arbitrated |
| N18 | Adapters and ports with a vague or partial name | P | | 2026-10-22: the rule applies as written (or as R3, R5, R9 set it); the new names arbitrated one by one in the lot | fixed in a lot |
| D1 | The Grype scan described as covering both images | L | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D2 | `AGENTS.md`'s single-test example path | L | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D3 | "Integration suites are not in the gate" | L | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D4 | `operate.md`: `amule.conf` written only if absent | V | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D5 | Shipped values called defaults | L | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D6 | `AGENTS.md`: "`application/` async use-cases" | V | R4 | settled by R4 and R14: `application/` described as use cases, steps and the lifecycle | fixed with that lot |
| D7 | `ports-imports.yml` allows `enum`, unused | V | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D8 | `testing.md`'s stale references and missing trigger | V | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D9 | `limits.md`: `no-new-privileges` "never confirmed" | P | | the docs follow the tree; its meaning (a CI run or a production node) checked before rewording | fixed by the docs block |
| D10 | `packages/matching/AGENTS.md`'s wrong path | V | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D11 | `BACKLOG.md`'s time-zone entry cites the wrong section | V | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D12 | The newest handoff's "Next" is stale | L | | the docs follow the tree (a fact, no question) | fixed by the docs block |
| D13 | Task names in help strings and `AGENTS.md` | V | | the docs follow the tree (a fact, no question) | fixed by the docs block |

## R. House rules to arbitrate

- **R1. The composition implements a driving port.** `CrawlerApp(CrawlerRunner)` (`composition/app.py:129`) and
  `PortSyncApp(PortSyncLoopRunner)` (`p2pwatch_amule/composition/port_sync_app.py:22`), each called by its command
  line. `AGENTS.md` says "a use case implements a driving port" and states no exception; the umbrella spec's D7 does
  (corrected 2026-10-18, lot 1a: `CrawlerRunner` "is implemented by the composition, since what it builds depends on
  the config the command line just read"); the 3b spec's table calls `PortSyncApp` a use case. (Corrected in the
  Discuss: lot 2's decision that a driving port serves an outside actor, never the composition, concerns who calls
  it; here the command line calls it, so it is not contradicted.) Nit beside it:
  `RunPortSyncLoop.run_port_sync_loop` reuses the port's method name without implementing the port, so a rename from
  the port misses it. Options: keep and write the exception in the rule; or the command line calls the composition
  root directly, with no port; or a use case implements the port and receives a builder.
- **R2. Where read models live.** "A driven read port returns domain types only" and "every read goes through a use
  case" together push read-side concepts into `domain/`: `PAGE_SIZE` (`domain/paging.py`), `CatalogEntrySort`,
  `SortDirection` (`domain/catalog_entry.py`), `ConsoleDatabase` and `QueryAnswer`'s text cells
  (`domain/console_query.py`), the interval cap. Lot 2's spec itself says "paging is not a domain concept". In CQRS
  and Clean Architecture the query side usually owns its read models. Options: keep them in the domain and correct
  the spec's sentence; or let a driven read port's file own its projections; or an `application/` read model.
  (Corrected in the Discuss, 2026-10-22: already decided. Lot 2's spec, "Conventions this lot sets": a read model
  owned by the port "would bypass the domain, which the operator refused"; "a type both sides use (`PeriodWindow`,
  the interval) lives in `domain/`", which covers the sorts, `ConsoleDatabase` and `QueryAnswer`; "paging is not a
  domain concept" places paging in the response model. Only `PAGE_SIZE` departs: it is in `domain/paging.py` and
  only `application/` reads it, so it moves there by the spec's intent.)
- **R3. An adapter implementing a Writer and a Reader; "Repository".** The rules split ports into Writer and Reader
  and never say "Repository", yet the adapters are `Sqlite*Repository`, the port error is `RepositoryError`
  (`ports/driven/repository_errors.py:11`, subclassed by `PersistenceError`), and `AGENTS.md`'s prose says "a
  repository". No rule names an adapter that implements both halves: `Sqlite<X>Repository`, `PosixAmuleConf`,
  `FilesystemDockerfile`, `InMemoryStatusBoard` follow four schemes. Evans uses Repository for the port itself.
- **R4. The status of `application/` modules that are not use cases.** About 14 of the crawler's 28 (`decisions`,
  `edge_state`, `matching_read`, `record_observations`, `reevaluate_catalog`, `search_tasks`, `search_worker`,
  `source_alerts`, `status_loop`, `supervise_loops`, ...) are internal steps of `RunCrawler`, free functions over
  `*Deps` bags where use cases are classes; `amule_bump`'s `body.py` and `release.py` are helpers. D7's correction
  ("internal steps of `RunCrawler`") never reached `AGENTS.md`, whose glossary reads "use case: an `application/`
  operation behind a driving port". To settle: what may live in `application/` besides use cases, and when a pure
  rule must go to the domain (A7, H1).
- **R5. A Reader over an outside system.** `RepoReader` (GitHub's API) and `ForwardedPortReader` (gluetun's control
  server) take the stored-state form, where Naming gives an outside system a capability name. Either reading of the
  rules is defensible today.
- **R6. The scope of "a check returns a report".** `ConfigChecker.check_config` and `ConfigValidator` raise
  (`ports/driven/config_checker.py:7`); `UnitCoverageChecker` returns `UnitCoverageReport | NoPerTestCoverage`;
  `problems` holds `str` (coverage, templates, formatted in the domain), `Violation` (vex, formatted by the command
  line) or `ClaimCoverageProblem` (a second vex type for the same concept); observability's `Report`
  (`domain/observability/policy.py:99`) uses the word for something else.
- **R7. A Writer that returns a value.** `SourcePointWriter.record_readings` returns the `RecordedReading`s with their
  roles (`ports/driven/source_points.py:19`), `DownloadWriter.record_queued` a `bool`
  (`ports/driven/downloads.py:18-20`), while lot 2's spec justifies the split as command-query separation.
- **R8. Logger names that are no module.** `AGENTS.md` (and `architecture.md:208`) says a use case logs "under the
  module's logger name"; port-sync logs under `p2pwatch_amule.adapters.driving.port_sync` and `...driven.gluetun`
  (`port_sync_app.py:50,59`), the dispatcher under `p2pwatch.observability`; none is a module. `migration-4x.md:157`
  documents them to operators, so they look kept on purpose. Options: the rule names the exception (operator-facing
  names are stable); or the names follow the modules, a v5 break recorded in `migration-4x.md`.
- **R9. One port per file, tach's granularity.** D6 gives "one module per port file" as what lets "exactly the ports
  it uses" be written, but port files bundle ports (`catalog.py` 5, `telemetry.py` 3, `client_status.py` 3,
  `node_id.py` 3) and `application`, `domain` and each adapter package are one tach module each: an adapter allowed
  `client_status` for `StatusClient` may import `ClientStatusWriter`. Options: one port per file; or accept the
  granularity and correct D6's wording in `AGENTS.md`.
- **R10. A port file's name.** Driving port files and most single-port driven files are named after their port
  (`catalog_finder.py`); 12 are named after a thing (`catalog.py`, `downloads.py`, `clock.py`, `telemetry.py`,
  `node_id.py`, `backoff_states.py`, `source_points.py`, `client_status.py`, `run_state.py`,
  `policy_fingerprint.py`, amule's `amule_conf.py`, `amule_bump`'s `dockerfile.py`); two repeat a domain module's stem
  (`policy_fingerprint`, `dockerfile`). The crawler bundles both clocks in `clock.py`, amule has
  `monotonic_clock.py`. Follows from R9.
- **R11. Where command-line defaults and repository paths live.** In a driving adapter for the crawler (`deploy/*.yml`,
  `cli/argparse_command_line.py:98-101`) and `amule_bump` (`--dockerfile`, `--body-file`); in `__main__` for
  `vex_checks` (`security/*.vex`, `ast-grep/rules`) and amule. C5 says a value taken when the operator sets nothing
  is the domain's; whether an option's default is such a value is open.
- **R12. Divergences from the literature, to confirm or reopen** (section L): one driving port per use case and every
  read through one; a full hexagon for each tooling package; a `ports/` ring of its own; the `Logger` port; ABCs only.
  Lead's view: confirm all but the first, whose cost shows in R2. (Corrected 2026-10-22: R2 turned out already
  decided; the first is confirmed by lot 2's choices as much as the others.)
- **R13. `CrawlerApp` and `PortSyncApp` named as the application** (raised in the Discuss of R1, 2026-10-22). They
  assemble the graph and run its root; "App" reads as the application, which is also the name of the use cases'
  ring. In Cockburn's terms they are the configurator ("aka Composition Root", Budapest 2023 deck, slides 15 and 19),
  Martin's `Main`. `__main__` and the composition are one ring (Cockburn's `main()` is the configurator); the split
  into two files exists only because the crawl's and port-sync's assembly waits for what the subcommand reads.
  Names to arbitrate one by one.

## A. The `p2pwatch` hexagon

Paths under `packages/crawler/src/p2pwatch/` unless noted.

- **A1. The run state read through raw `asyncio.Event`s.** The composition makes `shutdown` and `resumed`
  (`composition/app.py:258-264`) and hands them both to `AsyncioRunState` and straight to the core
  (`SearchTaskRunner`, `StatusLoopDeps`, `DownloadLoopDeps`, `RunCrawler`), which waits on them
  (`application/search_tasks.py:55`, `supervise_loops.py:19`, `status_loop.py:87`, `run_download_cycle.py:533`).
  `RunStateReader` has `is_paused` only (`ports/driven/run_state.py:22`). The glossary says `RunStateReader` reads the
  run state, shutdown included; `Waker` shows the port form (`wait`).
- **A2. Source point rules in the SQLite store.** `SqliteSourceRepository.record_readings`
  (`adapters/driven/persistence_sqlite/source_repository.py:99-135`) invokes `carried_role` (a domain function) on a
  point it reads in the transaction, validates contact points with `is_contact_point` and raises `PersistenceError`,
  drops readings with neither a source nor a name; `read_earlier_points` reduces rows into `EarlierPoints`. The
  policy value `time_between_source_reads` is computed in the config adapter (`config/crawler_config.py:99`).
  Against D8 and "a store decides no wait". The transaction's atomicity is why the role is decided there: any fix
  must keep it.
- **A3. Event dispatch orchestrated by a driven adapter.** `ObservabilityDispatcher`
  (`adapters/driven/observability/dispatcher.py:28-60`) describes, logs, applies metrics, notifies under a timeout and
  absorbs failures. `MetricsRecorder` and `Notifier` (`ports/driven/telemetry.py:10,18`) are imported by adapters
  only (`grep -rn "MetricsRecorder\|Notifier" packages/crawler/src | grep import`): ports that express no need of the
  core.
- **A4. Notification formatting in the domain.** `domain/observability/policy.py` builds Markdown and Discord bodies
  with emoji headings (`:117`, `:179-209`), shortens hashes "as the webui does" (`:218`), carries Prometheus naming
  notes. A deliberate earlier choice (E-D3), against D8's "formatting to the adapter".
- **A5. `CoverageReader` returns primitives.** `read_target_coverage() -> Mapping[str, tuple[str, ...]]`
  (`ports/driven/coverage_reader.py:11`): tiers by target id, not a domain type.
- **A6. The composition runs a startup step.** `backoff.load_from(backoff_states.read_backoff_states())`
  (`composition/app.py:315`); D7 makes startup steps internal steps of `RunCrawler`.
- **A7. Pure rules in `application/`.** `source_alert` with `FirstUseful` and `Reappeared`
  (`application/source_alerts.py:10-34`), the fresh-versus-persisted diff and the retraction rule in `rejudge_file`
  (`application/decisions.py:69-81`), `EdgeState` (`application/edge_state.py`). Against D8; depends on R4.
- **A8. Tier rules scattered and stringly typed.** "A catalog-tier decision is not an identification" in
  `domain/coverage.py:31` and twice in the webui (`adapters/driving/webui/app.py:158`, `:487`); `_FACET_TIER_ORDER`
  (`app.py:481`) re-encodes `TIER_RANK`; tiers and coverage statuses are bare `str`; `domain/coverage.py:29` points at
  an adapter's private function.
- **A9. The client and config error contracts.** `ApiRejectedError(ApiError, SearchFailedError,
  DownloadRejectedError)` (`adapters/driven/mule_api/errors.py:37`): a search refusal is catchable as a download
  refusal, and the application catches `DownloadRejectedError` on the `downloads()` listing and `sources()` reads
  (`application/run_download_cycle.py:65, 446, 501`) since no port says "read refused". `InvalidConfigError`
  (domain) is raised by a driven adapter and reaches the command line untranslated
  (`adapters/driving/cli/argparse_command_line.py:131`), where merge translates `CatalogCopyError` into `MergeError`;
  `ConfigError` (`adapters/driven/config/errors.py`) duplicates `InvalidConfigError`.
- **A10. Merge's same-catalog rule in two adapters.** `MergeCatalogs` resolves paths through `CatalogFinder`, passes a
  `destination_is_source` flag, and `SqliteCatalogCopier` resolves again to skip the destination
  (`sqlite_catalog_copier.py:163`).
- **A11. Read concepts in `domain/`.** See R2; the lot 2 spec's "paging is not a domain concept" is contradicted by
  `domain/paging.py`, used by `application/` only.
- **A12. `PosixProcess` owns the resource stack.** Its `__aenter__` returns the `AsyncExitStack` that closes the
  databases and the client (`adapters/driving/process/posix_process.py:24-40`): signal handling and the
  composition's lifecycle in one driving adapter.
- **A13. Config parsing placed two ways.** `matcher.yml` and `targets.yml` are parsed in the domain
  (`catalog_matching/domain/validation.py`), `crawler.yml` in an adapter; `AMULE_CLIENT_NAME` is defined in the
  config adapter (`crawler_config.py:73`).
- **A14. `DOWNLOAD_WAKE_SUBJECT`** is defined in `application/run_download_cycle.py:62` and imported by
  `application/decisions.py:22`: a contract between two loops held by one of them.
- **A15. `MatchingExplainer` builds its own `MatchingEngine`** from the config (`application/matching_read.py:38`)
  where the writers receive one (`composition/app.py:289`).
- **A16. `p2pwatch_testing`'s layout.** `catalog_rows.py` (SQLite-specific) and `virtual_time.py` at the package root;
  `adapters/mule_api/` without `driven/`; the webui's driving-port fakes in `application/fakes.py`.
- **A17. `node_id` passed on every driven call** (`record_observation(..., node_id)`, `emit(event, node_id)`), rather
  than held by the adapter. Informational: a design choice to confirm, not a defect.

## H. The five other hexagons

- **H1. `amule_bump`'s pure logic in `application/`.** `changelog_section`, `wrap`, `clip`, `fenced`
  (`application/body.py:45-83`), `is_newer`, `_version`, `_is_plain_version` (`application/release.py:16-37`);
  `BumpError` raised from both the application and the domain. Every other hexagon moved such logic to its domain.
  Depends on R4.
- **H2. Boot and port-sync read the environment in two rings.** Boot's driving port carries the raw `env`
  (`ports/driving/container_booter.py:11`), the command line forwards it, `BootContainer` parses it
  (`application/boot_container.py:39-43`); port-sync's composition parses it (`port_sync_app.py:29,48`), as
  `CrawlerApp` does. The 3b spec accepted `boot_container(env)`.
- **H3. `vex_checks` derives its root from `__file__` inside `main`** (`vex_checks/__main__.py:27`), where the other
  packages receive such values from the `__main__` guard; `tests/test_main.py:10,25` depends on the real VEX files.
- **H4. `vex_checks`' placeholder location.** The domain emits `"security"` (`domain/image_premises.py:44,53,64`),
  the application overwrites it with `dataclasses.replace` (`application/check_image_claims.py:51-52`): `Violation`
  mixes "a premise is falsified" and "a problem at a file".
- **H5. `vex_checks`' bijection in the use case** (`application/check_claim_coverage.py:39-82`), pure set logic,
  where `merge_claims` is in the domain and `coverage_checks` moved the same kind of logic there. The spec accepted
  it.
- **H6. Adapters hard-coding their tunables.** `timeout=30` (`amule_bump/adapters/driven/github_repo_reader.py:47`),
  `-T 60000` (`amule/adapters/driven/s6_service_supervisor.py:33`), where `GluetunForwardedPortReader` receives
  `timeout_seconds` from the composition.
- **H7. Two ways to run a command.** `GrypeVulnerabilityScanner` calls `subprocess.run` itself
  (`grype_vulnerability_scanner.py:22`), the amule adapters receive `run_command`, typed `Callable[..., object]` in
  two and `Callable[..., CompletedProcess[str]]` in `s6_service_supervisor.py:18`.
- **H8. Driving-port fakes in two places**: `tests/fakes.py` (amule, vex, coverage) or inline in the command line's
  test module (`template_checks`, `amule_bump`). Matters for "Contract tests for the fakes".
- **H9. pytest settings differ.** `--strict-markers` only in amule and the crawler; the `error::ResourceWarning` and
  `PytestUnraisableExceptionWarning` filters only in the crawler, though amule and `amule_bump` run loopback servers.
- **H10. An unparsable template**: `find_template_attributes` lets `TemplateSyntaxError` escape
  (`template_checks/domain/template_attributes.py:13`), `find_logic_constructs` reports it as a problem.
- **H11. `cwd` typed two ways.** `Path` in the vex and template command lines, `PurePath` in the crawler's and
  `amule_bump`'s; `_under_cwd` copied in four; vex's `_resolved_under_cwd` calls `.resolve()`
  (`vex_checks/adapters/driving/cli/argparse_command_line.py:110`), filesystem I/O in a driving adapter.
- **H12. `parse_grype_json` public and tested directly** (`grype_vulnerability_scanner.py:9`), where other adapters
  keep their parsers private.
- **H13. `Pin.arg_lines`** (`amule_bump/domain/dockerfile.py:13`) repeats the format `rewrite_pin` writes (`:24-26`),
  for the dry-run print only.
- **H14. `p2pwatch_amule`'s duplicated wiring.** `PosixAmuleConf` and `S6ServiceSupervisor` built twice
  (`__main__.py:39,65`, `port_sync_app.py:51,64`); boot's `S6ServiceSupervisor` receives a logger it never writes
  (`__main__.py:69`).
- **H15. The application raises a `FileNotFoundError` itself** (`run_port_sync_loop.py:94`) to reuse its `OSError`
  branch.

## N. Naming

Paths under `packages/<pkg>/src/`.

- **N1. Clock adapter files named against their class**: `wall_clock_system.py` (`SystemWallClock`),
  `monotonic_clock_asyncio.py` (`AsyncioMonotonicClock`), where amule's `system_monotonic_clock.py` and every other
  adapter file is its class in snake case.
- **N2. `persistence_sqlite/`'s three file schemes**: `*_repository.py` without the prefix, `sqlite_catalog_copier.py`
  with it, `catalog_read.py` (3 Readers), `local_read.py`, `observation_read.py`, `reader.py` by side; likewise
  `mule_api/client.py`, `observability/dispatcher.py`. Depends on R3.
- **N3. amuleapi spelled three ways**: the package `mule_api` (crawler and `p2pwatch_testing`), the class
  `AmuleApiClient`, amule's `amule_api_admin_password_setter.py`, the prose's `amuleapi`.
- **N4. `Posix`, `Filesystem` and `Json` prefixes**: amule's `PosixAmuleConf`, `PosixAmuledDirectoryPreparer`; the
  others' `Filesystem*`; vex's `JsonSarifWriter`, `JsonVexReader` name a format, close to the module naming the rule
  refuses.
- **N5. "Source" for two concepts**: `SqliteSourceRepository` (source points, local.db,
  `persistence_sqlite/source_repository.py:92`) and `SqliteSourceReader` (the catalog's sources, `catalog_read.py:511`).
- **N6. The status board's ports**: `ClientStatusWriter` and `ClientStatusReader` (`ports/driven/client_status.py:11,19`)
  store `StatusReading`s, their adapter is `InMemoryStatusBoard`, and they share their file with `StatusClient`.
- **N7. Display names with "Never" words** (`adapters/driving/webui/displays.py`): `FileRowDisplay` (`:146`),
  `SourceListRowDisplay` (`:356`), `BackoffEntryDisplay` (`:109`), `TimelineRowDisplay` (`:68`),
  `SourceHistoryRowDisplay` (`:326`, a file's sharing period, while `SourceHistory` is a source's page),
  `SourceFileRowDisplay` (`:368`, the same kind of thing, with `file: str`).
- **N8. `Download*` ports and "local state"**: `DownloadWriter` and `DownloadReader` hold tracked downloads
  (glossary: `tracked`); `SqliteLocalStateRepository` stores the node id and the fingerprint, `SqliteNodeStateReader`
  reads `NodeState`: "local state" has no glossary line.
- **N9. Fakes named after no port**: `FakeCatalogReader` (`p2pwatch_testing/application/download_fakes.py:215`,
  implements `DecisionReader` and `ObservationReader`); `FakeSourcePointStore`, `FakeDownloadStore`,
  `FakeNodeIdStore`, `FakeFingerprintStore`, `_FakeFingerprints`; `FakeCrawlControls` ("control" is a Never word);
  `FakeDownloadStore`'s `fail_active_states` ("active").
- **N10. Doubles without the `Fake` prefix**, about 16: `TickingWallClock`, `TickingMonotonicClock`, `LoopWallClock`,
  `LoopMonotonicClock`, `_RecordingNotifier`, `_RaisingNotifier`, `_HangingNotifier`, `_RecordingWaker`,
  `_BlockingMonotonicClock`, `_LaggingDownloadStore`, `_ScriptedClient`, `_TimedEventEmitter`; the leading
  underscore varies too.
- **N11. `last` for the most recent**: `DownloadReader.read_last_seen_at_by_file` (`ports/driven/downloads.py:49`),
  `TrackedDownload.last_progress_at`, `KnownSource.last_seen_at`, `SourceNaming.last_seen_at`; only `SharingPeriod`
  pairs `last` with `first`.
- **N12. Abbreviations outside the glossary**: `*Deps` and `deps` (about 135 uses); `repo` (`catalog_repo`,
  `local_repo`, `RepoReader`, `repo_root`, 8 log messages in `run_download_cycle.py`, e.g. `:474`); `dir`
  (`templates_dir`, `static_dir` in `webui/app.py:692`; amule's `INCOMING_DIR`, `TEMP_DIR`, which echo `amule.conf`'s
  keys); `conn` (about 33 in `p2pwatch_testing`); `KeywordDef`, `RegexDef`, `AttrBetweenDef`, `TokenRef`,
  `AttrBetweenMatcher` (matching); `SourceMeta`, `raw_meta`; `doc`, `out`.
- **N13. `ed2k_hash` past the mapper**: about 25 uses in `p2pwatch_testing/catalog_rows.py`.
- **N14. Generic local names**: `result`, `payload`, `item`, `entry`, `value` (about 39), mostly in
  `mule_api/mapping.py`, `config/crawler_config.py`, amule's `domain/settings.py`.
- **N15. Stale words in prose**: "layer" in about 20 docstrings (`domain/__init__.py:1`, `composition/app.py:3`,
  `application/decisions.py:3`); `adapters/__init__.py:1` says "EC" and holds a long dash; "sync repos"
  (`application/record_observations.py:3`), "sighting" (`sqlite_catalog_copier.py:10`), "control POST"
  (`webui/app.py:546`), "notif" (`domain/observability/policy.py`).
- **N16. Driving port names**: `CrawlerRunner.crawl` (`ports/driving/crawler_runner.py:11`), where the pattern is
  verb plus object (`run_port_sync_loop`); `ConsoleQueryOutcome` (`ports/driving/console_query_runner.py:10`), named
  from no verb. Depends on R1 for the first.
- **N17. Writers' verbs for one act**: `record_node_id`, `set_policy_fingerprint`, `save_backoff_states` (the last two
  share an adapter); `write_*` elsewhere.
- **N18. Vague or partial names**: `CoveragePyReader` (implements `TestCoverageReader`), `ObservabilityDispatcher`
  (implements `EventEmitter`), `ReaderProvider` (`reader.py:47`), `AccountManager`; `telemetry.py` beside the domain's
  and adapters' `observability`; the spec's `CatalogScanner` is `CatalogScanReader` in code.

## D. Guidance and docs against the tree

- **D1. The Grype scan described as covering both images.** `AGENTS.md:41`, `SECURITY.md:28-31,66-68`,
  `docs/contributing/testing.md:355-356`, `docs/verify-image.md:54-59`; `.github/workflows/grype-scan.yml:20-26` has
  one leg, `mulewatch`. The backlog's "The Grype scan back on p2pwatch at the v5 release" states the future these
  documents present as current.
- **D2. `AGENTS.md:74`'s single-test example** runs `tests/test_engine.py::...`; the file is
  `packages/matching/tests/domain/test_engine.py`.
- **D3. "Integration suites are not in the gate".** `AGENTS.md:81`, `testing.md:31-33,69-71`; in CI the required
  check `gate` needs `build-and-verify` (`validate.yml:216`), which runs the four markers on both architectures.
  `testing.md:358` ("Tous les markers tournent désormais en CI") contradicts its own section 1. True of the local
  gate (`poe check`, the pre-push hook), false of the merge gate.
- **D4. `docs/operate.md:23-24`**: `amule.conf` written "seulement s'il n'y en a pas"; boot reconciles it every time
  (`p2pwatch_amule/domain/conf.py`, `reconcile_conf`).
- **D5. Shipped values called defaults**: `docs/settings.md:12` (a node downloads "par défaut"), `:55` (metrics "9090
  par défaut, actif par défaut"), `docs/operate.md:358-359` (`/data/*.db` as "Valeur par défaut", both keys
  required), `docs/contributing/architecture.md:675`. In code `DEFAULT_DOWNLOAD_ENABLED = False`
  (`domain/config_defaults.py:15`) and an absent `observability.metrics` serves none; only `deploy/crawler.yml` sets
  them.
- **D6. `AGENTS.md`: "`application/` async use-cases"**: half its modules are portless internal steps, the webui's use
  cases are synchronous. Depends on R4.
- **D7. `ast-grep-rules/ports-imports.yml:11` allows `enum`**, which no port imports.
- **D8. `docs/contributing/testing.md`**: `:358-359` refers to other packages' sections that do not exist; `:69` says
  each package's `addopts` deselects the markers (only the crawler's has them); `:334-335` omits `release.yml`'s
  trigger on every push to `main`.
- **D9. `docs/limits.md:90-91`**: `no-new-privileges` with the privilege drop "jamais confirmé sur une machine
  réelle", while the compose smoke runs that combination in CI on both architectures. P: it may mean a production
  node.
- **D10. `packages/matching/AGENTS.md:6`** places `yaml_loader.py` in the matching package (it is the crawler's);
  `:16` still calls the `match_decisions` columns "future".
- **D11. `BACKLOG.md:25`** sends the time-zone entry to section 6 of `2026-10-13-append-only-source-points.md`, which
  is "Blocks"; the text is a line of its "Adjacent backlog items" (`:442`).
- **D12. The newest handoff's "Next"** (`2026-10-21 - handoff - five hexagons 3c.md:310-312`) says the operator reviews
  and merges the stack; it is merged.
- **D13. Task names**: `code-pattern-check`'s help omits the Protocol-base and core-builtins rules; `AGENTS.md:69`
  writes `unit-coverage-check` for `_unit-coverage-check`.

## L. House conventions against the hexagonal literature

| Convention | Against the literature | Sources |
|---|---|---|
| Rings from the path, `ports/` a ring of its own | Partly: driving and driven are Cockburn's primary and secondary; Hombergs and Graça put the ports in the application layer (`application/port/in`, `out`) | Cockburn; Graça, "Explicit Architecture" |
| Every port an ABC, `Protocol` refused | Aligned with cosmicpython (`AbstractRepository`); the Python community is split, and a blanket ban is stricter than anyone recommends, defensible when every implementer is ours | cosmicpython |
| One driving port per use case, every read through one | Partly divergent: Cockburn writes that a port per use case produces "hundreds of ports" and "neither extreme appears optimal" (fetched); Hombergs and Martin do use one input boundary per use case; CQRS read sides often query directly | https://alistair.cockburn.us/hexagonal-architecture/ |
| Agent-named ports, no `Port`, `UseCase`, `Repository`; Reader and Writer | Naming divergent (Hombergs `...UseCase`, `...Port`; Evans and cosmicpython `Repository`); Cockburn's "For doing X" is the nearest; the split matches CQRS, usually applied to models rather than to every port | |
| Response models in the driving port's file, view models in the UI | Aligned (Martin's Response Model, Presenter and View Model) | Martin, "Clean Architecture" |
| The composition only wires, tested by wiring tests | Aligned (Seemann's Composition Root, thin, integration-tested) | Seemann |
| Loop roots without a driving port | Aligned (a long-running process has nothing to abstract); undercuts "no exceptions" | |
| Adapters depend on ports only, never on another adapter | Aligned (Martin, Graça, Hombergs) | Graça |
| A full hexagon for each tooling package | Divergent: the literature fits the structure to the complexity (YAGNI; cosmicpython warns against it for small tools) | |
| Fakes inherit the port; contract tests planned | Aligned (cosmicpython's `FakeRepository`; Freeman and Pryce, Seemann on contract tests) | |
| Logging through a `Logger` port | Stricter than usual (cosmicpython uses `getLogger` in the core), consistent | |
| Two clock ports | Aligned (time injected; Seemann calls Ambient Context an anti-pattern); the wall/monotonic split is more precise than usual | |
