# Hexagonal architecture: rings, ports and hexagons

Status: umbrella spec of the three lots in D18, settled in Discuss on 2026-10-17 and 2026-10-18, reviewed
(`.reviews/hexagonal-architecture-spec.md`), approved by the operator on 2026-10-18; a claim corrected after
that approval says so. No block runs from it: each
lot gets its own spec and block table, which cites this one for the decisions already taken and re-measures,
against the tree the previous lot leaves, every number it acts on. It is committed with lot 1's spec, in that
lot's first block's first commit (Corrected 2026-10-18, at the operator's request: committed to `main` on its
own, with the backlog entry that points to it, so that a new session starts from both).

## Why

The operator asked that the application follow Clean Architecture (Robert C. Martin), ports and adapters
(Alistair Cockburn) and hexagonal rules, with one convention applied everywhere rather than a rule with
exceptions judged case by case: with agentic programming, a uniform convention keeps the codebase
maintainable, and the redundancy it costs (delegating functions, ports with one adapter) is cheap next to
the ambiguity it removes. Boundaries are wanted for clarity, testability and rules a tool enforces, not only
to swap an adapter.

The work absorbs two `BACKLOG.md` entries: "The ports and the composition's architecture" (section "For the
architecture lot" of `agents/specs/2026-10-17-serena-and-the-language-servers.md`) and "The webui's read
side" (section 7 of `agents/specs/2026-10-13-descriptive-names.md`).

## Out of scope

Nothing an operator sees changes but D14's commands: both databases' schemas, the webui's routes and pages,
`crawler.yml`'s keys, the metrics, the notifications and the compose environment stay as they are. A reader
notices a breach as a migration file, a route or a key in a lot's diff outside D14.

## Measurements (2026-10-17)

Taken on `main` at `a6afe6d` by the lead and a measuring agent, recounted by the spec review; the scripts and
the tach trials lived in the session scratchpad, which does not survive the session, so each lot re-runs what
it relies on.

- **Imports between today's layers** (crawler): `domain` imports only itself and `catalog_matching`; `ports`
  imports `domain` and `catalog_matching`; `application` imports `domain`, `ports` and `catalog_matching`,
  never an adapter; no module under `adapters/` imports another adapter (its 21 `p2pwatch.adapters` imports
  are internal to one adapter). Against the target rules, mapped onto today's paths with tach 0.35.3: 34
  violations, all in the webui (32) and `merge` (2): the webui's readers import `webui.domain` (13) and
  `persistence_sqlite` (6), the Starlette module imports the four readers (12) and `persistence_sqlite` (1),
  `merge` imports `persistence_sqlite` (2).
- **tach 0.35.3** (PyPI, released 2026-10-06), on a copy of the tree: with layers `composition` >
  `adapters` > `core` and `depends_on` inside the core, it refuses `domain` importing `application`, an
  adapter importing another (`rng_random` importing `mule_api`) and `ports` importing `composition`; it
  accepts an injected `import sqlite3` in `domain`, since it only checks imports between modules of the
  project. Under the default `root_module`, code no declared module owns is not checked at all; with
  `root_module = "forbid"`, an import into or out of such code fails. A module that does not exist is a
  warning; with `exact = true`, a `depends_on` naming a missing module fails.
- **tach exceptions**: an inline `# tach-ignore` is fragile under ruff's import merging, narrowing loudly or
  widening silently depending on how the statement wraps, and a directive on the preceding line must list
  every name on one line (186 characters for `catalog_read.py`'s ten names, against `line-length = 100`). A
  dependency declared `{ path = ..., deprecated = true }` in `tach.toml` is allowed and reported as a warning
  at each import; once no import uses it, `exact = true` fails (exit 1); a new edge beside it still fails.
- **`Protocol` classes under `packages/*/src`**: 26 (`grep -rhE "^class \w+\(.*Protocol" --include='*.py'
  packages/*/src | wc -l`). 7 are outside `ports/`: `DownloadRepository` and `DownloadCatalogReader`
  (`application/run_download_cycle.py`), `DownloadSourceClient` and `WebuiServer` (`composition/app.py`, which
  imports `AmuleApiClient`: inheriting `DownloadSourceClient` would be an import cycle), `Matcher`
  (`catalog_matching/combinators.py:12`), and the I/O seams of `amule_bump/github.py` and `vex_checks/grype.py`.
- **Methods declared by two ports**: `connect` in `SearchClient`, `StatusClient` and `DownloadClient`;
  `close` in `SearchClient` and `DownloadClient`; `download_candidates`, `latest_observation` and
  `best_observation` in both `CatalogRepository` (10 methods) and `DownloadCatalogReader` (3); `now` in
  `WallClock` and `MonotonicClock`, two operations no class implements together.
- **`connect()` is a no-op after the first success**: `AmuleApiClient` resets its transport only in
  `close()`, and a daemon restart surfaces as a `401` that its re-login renews; the comment at
  `application/run_download_cycle.py:477` ("re-arms a stream the adapter discarded") dates from EC.
- **Logging in the core**: 27 `_logger` calls in 5 modules of `application/`, each holding a
  `logging.getLogger(...)` global.
- **The composition's tests**: `tests/composition/test_app.py` (1,578 lines) drives `composition/app.py`
  (581) through injected factories (`_client_factory`, `_download_client_factory`, `WebuiServer`)
  (Corrected 2026-10-18: through more seams than these three, `metrics_server`, three `monkeypatch.setattr`
  targets and three private methods among them, and `tests/integration/test_crawler_loop.py` uses
  `client_factory` too); `test_main.py` (303) monkeypatches `composition/__main__.py`, and 16 of its 19 tests cover the command
  line's own logic (exit codes, `validate-config`'s rejections and defaults, the bare invocation).
- **The amuleapi endpoint** is a code constant, `ed2k:4711` (`adapters/config/crawler_config.py:60-61`).
- **The webui's readers build its response models**: `webui/adapters/catalog_read.py` imports 10 types of
  `webui/domain/views.py`, `local_read.py` 3.
- **The webui bind** is fixed at `0.0.0.0:8080` in code, and 8080 is in use on the operator's machine (the
  deployed node publishes it). A collision is silent today: uvicorn 0.54.0 calls `sys.exit` on a failed bind,
  `CrawlerApp._serve_webui` (`composition/app.py:384-391`) catches `Exception` only, so the webui thread ends
  without its "degraded" log, after a "webui serving" line logged before the bind is attempted.
- **Size, measured step by step against the tree each step leaves**: about 10,500 counted lines (the hunk
  metric of `agents/workflow.md`), 4,000 of them mechanical, in about 26 blocks, 6 of them taking the size
  exemption. A `git mv` with one rewritten import counts 1 line and 1 file; a file split counts twice (its
  deletion and addition hunks), and so does a moved file git no longer pairs (under 50% similarity).

## Decisions

- **D1. Rings.** Every hexagon is a core (`domain` < `ports` < `application`) surrounded by adapters, with
  the composition on top; imports point inward only, and adapters never import one another. Why: the
  dependency rule of Clean Architecture; the operator chose rings over five strict layers, since in
  hexagonal terms the ports belong to the core.
- **D2. The ring is read from the path**, on one schema in every package:
  `<pkg>/{domain,ports,application,adapters,composition}/`, with `ports/driving/`, `ports/driven/`,
  `adapters/driving/` and `adapters/driven/`; a package has only the rings it needs. Why: an agent knows
  where a new module goes, the tool's configuration follows from the paths, and the driving/driven split
  is what lets D6 refuse a route that calls a repository past its use case.
- **D3. Six hexagons, which never import one another**: `p2pwatch` (the crawler, its webui, `merge`, and
  `catalog_matching`, which is its domain ring in its own distribution package, under
  `catalog_matching/domain/`), `p2pwatch_amule`, `vex_checks`, `template_checks`, `coverage_checks` and
  `amule_bump`. Tests and `p2pwatch_testing` are outside the ring rules (not D4's ban). (Corrected 2026-10-19:
  no tool refuses a cross-hexagon import its package declares, so a test holds the workspace's internal
  dependencies to `p2pwatch` on `catalog_matching` and on its test support; lot 1b's spec, "The check".) Why: a hexagon is
  one application with its use cases, not a package; the crawler, the webui and `merge` share one domain,
  one database and one schema (the webui runs in the crawler's process), so the imports measured between
  them are one hexagon cut along the wrong axis. The tooling packages follow the rule because a convention
  with exceptions is where an agent improvises. A test assembles pieces of several rings by nature.
- **D4. Every port is an ABC** that its implementers inherit, driving and driven alike, fakes included, and
  no `Protocol` is left under `packages/*/src`, `Matcher` and `p2pwatch_testing` included; an ast-grep rule
  refuses one, covering each hexagon from the lot that leaves it with none (D17). Why: renamed from an ABC,
  pyrefly reaches every override (bench 11: 75 sites in 12 files, against 4 from a `Protocol`), which holds
  for any hierarchy, a port or not; an adapter that inherits its port imports it, so tach sees and checks the
  link D6 states, where a structural implementation imports nothing; mypy refuses to instantiate an
  incomplete implementation. The breakages bench 11's lot listed (`@runtime_checkable`, `__slots__`, the
  attributes in ports, the `tests.*` import gap) are lot 2's, from that section.
- **D5. A port is one cohesive capability, phrased by the core's need, and each operation is declared by
  exactly one port.** No port inherits another; there are no intersection types (`MuleClient`,
  `DownloadSourceClient`); a consumer depends on as many ports as it needs, an adapter inherits as many
  ports as it implements, and the composition passes the concrete adapter to each consumer typed by the
  port it expects. `CatalogRepository`, a header interface mirroring its adapter, splits into role ports.
  `WallClock.now` and `MonotonicClock.now` are two operations, and no class implements both. Why: the
  duplicates measured come from cutting ports both by provider and by consumer; with disjoint operations a
  multiple ABC inheritance has no rename trap, and no general repository has to extend a use case's view,
  which the operator found semantically wrong.
- **D6. Each adapter depends on the ports of its own side that it uses, plus the domain**: a driving adapter
  on driving ports only; a driven adapter on the driven ports it implements and those it consumes (the
  amuleapi client and the SQL console hold a `MonotonicClock`); a use case implements a driving port and
  consumes driven ports. `CrawlerControl` and `StatusReadings` become driving ports implemented by use
  cases, over driven ports that `LoopCrawlerControl` and the status board implement; the webui's HTTP module
  stops importing the clock ports. tach states it with one module per port file, `depends_on`,
  `layers_explicit_depends_on` and `exact`, and isolates each hexagon with `visibility` (Corrected 2026-10-19: with `tach check-external`, D15). Why: the same rule
  on both sides; one module per port file is what lets "exactly the ports it uses" be written.
- **D7. Every use case has a driving port**, and every read goes through a use case, even a pure
  delegation (Corrected 2026-10-18: one driving port, `CrawlerRunner`, is implemented by the composition, since
  what it builds depends on the config the command line just read; lot 1a's spec). Why: one rule with no exception to judge, and a driving adapter's test receives a typed fake
  of its use case; the operator accepts the delegating functions and the rename in two places this costs.
- **D8. Each boundary owns its data types.** A domain concept crosses any boundary as itself: `FileKey`,
  `SourceKey`, and the one observation into which section 7 of `agents/specs/2026-10-13-descriptive-names.md`
  collapses `Sighting`, `ObservedFile` and `ReevalRow`. A read projection has the driven port's own types
  (section 7's `<Thing>Record`), which the use case maps into the response models of its driving port;
  response models live with their driving port in `ports/driving/`; business rules go to the domain, and
  view models (section 7's `<Thing>Display`) and formatting to the HTTP adapter, whose presenter produces
  them. Why: a driven adapter cannot see a driving port (D6), storage and screen evolve apart, and the
  mapping is where read logic will land; a page-shaped row with its counts and facets is not a domain
  concept, and reusing the driven types on the driving side would undo D6.
- **D9. No I/O in the core outside a port**: a per-ring allowlist of what the core may import, enforced by
  ast-grep, every other import refused. The base is the pure standard library the core uses today
  (`abc`, `collections`, `collections.abc`, `contextlib`, `dataclasses`, `datetime`, `enum`, `functools`,
  `hashlib`, `ipaddress`, `itertools`, `re`, `typing`, `unicodedata`, `urllib.parse`), plus `rapidfuzz`
  (`catalog_matching`) and `packaging.version` (`vex_checks`); `asyncio` and `uuid` are allowed by symbol
  (the task, event and wait primitives and the `sleep(0)` yield; `uuid5` and `UUID`), since both also hold
  I/O or entropy. The `logging` calls of `application/` go through a logging port (its name is lot 2's);
  until then `logging` sits in `application`'s list beside a comment naming lot 2, which removes it. Why: an
  allowlist is safe by construction and adding a module is a visible line; tach does not check third-party
  imports; a `getLogger` global is a dependency no signature shows.
- **D10. The amuleapi adapter reconnects itself**: a call finding its transport closed reopens it under an
  `asyncio.Lock` (the search and status loops share one session); `connect` and `close` leave every port;
  the composition opens the concrete adapter at startup (a wrong password still fails the start, a daemon
  not yet listening is still tolerated) and closes it. Why: only the adapter knows its transport's state,
  and a use case forgetting `connect()` is the class of defect behind a past 7-day wedge; the measurement
  shows the loops' calls are already no-ops after the first success.
- **D11. The composition only wires, without injected factories, and is tested in integration.** The client
  factories, `WebuiServer` and the intersection types go, with `test_app.py`. The command line (argument
  parsing, subcommands, `validate-config`, the exit codes) is a driving adapter with its own unit tests,
  `test_main.py`'s 16 command-line tests moving with it; `__main__.py` only delegates. `coverage_checks`
  learns that the composition ring is covered by the gate-run integration tests instead of its own unit
  tests, and the package's 100% branch coverage still measures it, so a composition line no wiring test runs
  fails the gate. `AGENTS.md`'s coverage rule says so. (Corrected 2026-10-18: the logic the composition holds
  today moves out to units with their own tests, and `coverage_checks` needs no change, since the wiring
  tests live in `tests/composition/test_app_wiring.py` and `tests/test_main.py`, which it already counts as
  the composition's own tests; lot 1a's spec.) Why: wiring is a concern between units, its unit tests
  drive fakes through seams that exist only for them, mypy already refuses a wrong adapter, and rewriting
  1,578 lines of tests for a composition the other decisions reshape would be lost work; parsing and exit
  codes are logic, not wiring.
- **D12. What justifies an integration test**: a fact the unit tests take for granted, one we do not
  control (a daemon, the kernel, Docker, the assembly at runtime), which if false leaves the unit gate green
  and production broken. Each integration test names the fact it proves and tolerates what is not ours (an
  empty search). A fact a type or a unit test can carry moves there. Where a test runs is decided only by
  the resource it needs: one that needs none runs in the gate, like lot 1's wiring tests against an
  amuleapi fake served on a loopback socket (new, about 80 lines in `p2pwatch_testing`; today's fake is an
  `httpx.MockTransport`) (Corrected 2026-10-18: about 45 lines). Why: the unit tests' doubles are our beliefs about the outside; the integration
  test checks the belief, not the logic.
- **D13. The webui bind and the amuleapi endpoint are value parameters of the composition root**, not
  factories: `__main__` passes the production values (`0.0.0.0:8080`, `ed2k:4711`), a test passes
  `127.0.0.1:0` and its loopback fake. A failed bind surfaces: the composition watches uvicorn's start and
  logs the webui degraded when it does not start, `SystemExit` included (Corrected 2026-10-18: the webui's
  HTTP adapter watches it, in `UvicornServerThread`, not the composition); the wiring test asserts a request
  answered on the port the server bound. `AGENTS.md`'s bind invariant becomes "fixed in `__main__`". Why:
  the gate checks the wiring without an operator-facing key, and the silent collision measured today is a
  latent defect, fixed rather than tested around.
- **D14. A package root holds only `__init__.py` and `__main__.py`**, and `__main__.py` always dispatches an
  explicit subcommand, even when a package has only one: `python -m p2pwatch crawl` (the image's `CMD`),
  `validate-config` and `merge`; `python -m p2pwatch_amule boot` and `port-sync`; `python -m vex_checks`
  with the two checks the workflows run and the two poe runs; `template_checks`' two and `coverage_checks`'
  entry points, which poe calls; `python -m amule_bump bump`. (Corrected 2026-10-18: four packages gain a
  root `__main__.py`, `p2pwatch_amule`, `vex_checks`, `template_checks` and `coverage_checks`;
  `coverage_checks` has a single entry point, `unit-coverage`; `py.typed` stays at the root beside them.) The bare `python -m p2pwatch --config ...` and
  `python -m p2pwatch.merge` are refused: two v5 breaks, recorded in `docs/migration-4x.md`, and
  `docs/operate.md` and `docs/troubleshooting.md` follow. Why: one form, and adding a command never renames
  an existing one; the node is a compose stack, so commands are rarely typed.
- **D15. tach enforces the boundaries, ast-grep the allowlists and the `Protocol` ban.** tach runs in
  `lint-all` with `layers`, `layers_explicit_depends_on`, `exact`, `forbid_circular_dependencies`,
  `visibility` and `root_module = "forbid"`, the root `__main__.py` modules declared in the composition
  layer. (Corrected 2026-10-19: `tach check-external` in place of `visibility`, which no import
  across distributions reaches; lot 1b's spec, section "The check".) (Corrected 2026-10-19: `check-external`
  refuses only an undeclared import, as deptry did; a test of the workspace's internal dependencies holds the
  declarations themselves, D3.) An exception is a dependency declared `deprecated = true` in `tach.toml`, beside a comment naming
  its reason and the lot that removes it; no `# tach-ignore` is written. Why tach rather than import-linter:
  the operator's choice, after the trial proved it refuses the three violation shapes and its gap
  (third-party imports) is covered by D9. Why deprecated edges: they live in one file, survive ruff and
  line length, fail once unused, and still refuse a new edge; `root_module = "forbid"` makes a module a lot
  forgets to declare fail instead of going unchecked.
- **D16. Moves are `git mv` plus a scripted import rewrite**, mypy and pytest verifying them; each file
  goes to the ring of its largest part, and only the smaller parts are extracted afterwards (Corrected
  2026-10-18: a module that does I/O goes to an adapter even if most of it is logic, and where a placement
  would have the core import an adapter, the imported piece moves into the core at once; lot 1b's section
  "Where each module goes"). Strings no
  checker sees are rewritten by hand and listed in each move block: logger names spelling module paths,
  paths in `pyproject.toml`, `parents[N]`, fixture paths named as strings, `CMD`, `entrypoint.sh`, the s6 run
  scripts, the workflows' `python -m` lines, and the module paths in `docs/` (`docs/operate.md`,
  `docs/contributing/architecture.md`). Why: Serena renames symbols, not modules; a split counts twice under
  the hunk metric.
- **D17. The gate comes after the moves, with the target rules.** tach's remaining violations are
  deprecated edges; each later lot declares the modules it creates and deletes its own edges, which `exact`
  enforces. The allowlist covers every core ring from lot 1 (its one exception D9's `logging`); the
  `Protocol` ban covers each hexagon from the lot that removes its last `Protocol` (lot 2 for `p2pwatch`,
  lot 3 for the others), so ast-grep carries no ignore that could go stale unseen. Why: tach checks nothing
  in code no declared module owns, so rules written before the moves would check nothing, and the moves add
  no code to protect.
- **D18. Three lots, in this order, each with its spec and stack**:
  1. **Foundations**: `coverage_checks` learns the composition ring (Corrected 2026-10-18: it needs no
     change, D11); the loopback amuleapi fake and the wiring tests, then the composition loses its
     factories; every package moves to D2's paths and D14's entry points; the gate (D15, D17). About 8
     blocks, mostly mechanical.
  2. **The `p2pwatch` hexagon**: the session (D10) and the logging port (D9); the webui's read side and
     `merge` (D7, D8, with section 7 of the descriptive-names spec); then the ports as ABCs and their role
     split (D4, D5). About 10 blocks, mostly new code. The conversion comes last because converting first
     would declare `connect` abstract in three ports for D10 to delete, and convert ports the webui's read
     side rebuilds.
  3. **The five other hexagons** (their I/O behind ports, each package's tests off `monkeypatch`), and
     the documentation left over. About 8 blocks; the least certain estimate. (Corrected 2026-10-19: lot 3
     also names the entry functions the command lines call, still `main`, after their operation, and gives
     each check one word across its module, subcommand and parameter; lot 1b's holistic review.)

  (Corrected 2026-10-18: `merge` moves to a use case in lot 1 instead of lot 2, and lot 1 becomes two lots,
  each with its stack and holistic review: 1a, the composition and the command line, and 1b, the moves, the
  entry points and the gate; `agents/specs/2026-10-18-hexagonal-foundations.md`.)

  Why: one stack of 26 pull requests means rebase cascades and a review no one does in one sitting (D12
  of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`); a lot measured on the tree its
  predecessor really leaves is estimated better than a step measured on a projected one, which the
  operator required since each step builds on the previous.
- **D19. `AGENTS.md` changes with the lot that makes it false.** Lot 1: the "Clean / Hexagonal" hard rule,
  the coverage rule, the "Where the code lives" table, the package boundary and standalone tool invariants,
  the bind and the `ed2k:4711` invariants, and the glossary lines for `ring`, `hexagon`, `driving`, `driven`
  and `use case`. Lot 2: the webui and `merge` rows, the Gotchas that assume `Protocol` ports (the one-line
  stub idiom, which becomes the `@abstractmethod` one, and the Serena rename from each implementer), the
  invariant on the adapters that hold a `MonotonicClock`, and the glossary lines for the read side's types.
  Lot 3: the TID251 exemption of `packages/amule/` (once port-sync has a clock port) and
  `docs/contributing/architecture.md`. Why: a rule file that lags the tree misleads every agent that reads
  it, and the Naming rule wants a new concept's glossary line in its lot.
- **D20. `BACKLOG.md`**: lot 1's first commit replaces the two absorbed entries with one entry for lot 2 and
  one for lot 3, each pointing here (Corrected 2026-10-18, at the operator's request: replaced before lot 1
  by one "Hexagonal architecture" entry with a sub-item per lot, each sub-item deleted when its lot ships);
  lot 2's entry also points to section 7 of
  `agents/specs/2026-10-13-descriptive-names.md` and the section "For the architecture lot" of
  `agents/specs/2026-10-17-serena-and-the-language-servers.md`, which lot 2's spec inherits and which stay
  authoritative for what this spec does not restate (the inherited names, the dead `{% else %}` at
  `sources.html:26`, the ABC breakages). An entry is deleted when its lot ships. Why: the backlog says what
  is intended next, without losing the detail the absorbed entries pointed to.

## Open

- **Names**, arbitrated one by one in the Discuss of the lot that introduces them: the logging port, the
  role ports replacing `CatalogRepository`, the query use cases and their ports, and the response models'
  suffix beside section 7's `Record` (driven projection) and `Display` (view model).
- **Each ring's exact allowlist**, starting from D9's list and fixed by lot 1's gate block.

## Adjacent backlog items

- **"Contract tests for the fakes"** stays open: it is D12's systematic form for driven adapters, but its
  suites are written once per port, so they wait for the ports' final shape at the end of lot 2.
- **"Test quality"** stays open: pruning tests that lots 1 and 2 delete or rewrite would be lost work; it
  comes after lot 2.
- **"Mutation testing in the gate"** stays open, for the same reason, after "Test quality".
- **"The logic-free template guard on Jinja's syntax tree"** stays open: it moves logic from templates
  into view models, which D8 places in the HTTP adapter; it is a separate tool and can follow lot 2.
- **"Adopt ty"** stays open: D4 rests on pyrefly's rename of a nominal hierarchy, which the ty parity
  conditions already track.
- **"Multi network, stage 5"** stays open: its new clients will be adapters under these rules, so it comes
  after lot 2.
- **"Sort the files view by first seen"**, **"The webui in the visitor's time zone"**, **"A copy before a
  migration that rewrites rows"** and **"Every stamp an integer of microseconds"** stay open: none concerns
  the rings; a webui entry done before lot 2 is rewritten by it, so those two are better after it.
