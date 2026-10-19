# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`p2pwatch` continuously surveils the eMule network (eD2k + Kad, via an aMule client driven over amuleapi, its REST surface) to recover lost-media episodes of the French dub of *Keroro mission Titar* (aired 2008 on Teletoon), cataloguing all available metadata along the way.

It is a **virtual uv workspace** with eight packages: `packages/crawler/` (package `p2pwatch`, dist `p2pwatch`), `packages/amule/` (package `p2pwatch_amule`, dist `p2pwatch-amule`, stdlib only, the aMule container's boot step and port-sync), `packages/matching/` (package `catalog_matching`, dist `catalog-matching`, shared domain), `packages/crawler_testing/` (package `p2pwatch_testing`, dist `p2pwatch-testing`, the crawler's shared test support: fakes, catalog rows, a virtual event loop), and four dev/CI tooling packages never shipped in a prod image: `packages/vex_checks/` (package `vex_checks`, dist `vex-checks`, reads `security/*.vex.openvex.json` to keep our OpenVEX claims honest), `packages/template_checks/` (package `template_checks`, dist `template-checks`, keeps the webui's Jinja templates logic-free: `poe template-check`, and lists the names they read for `poe dead-code-check`), `packages/coverage_checks/` (package `coverage_checks`, dist `coverage-checks`, checks that each module is covered by its own tests, the test files mirroring `src`: run by `poe test`) and `packages/amule_bump/` (package `amule_bump`, dist `amule-bump`, stdlib only, run by `.github/workflows/amule-bump.yml` to bump the aMule pin and write the PR body). The crawler package `p2pwatch` also contains the in-process webui subpackage `p2pwatch.adapters.driving.webui` (read-only catalog viewer + light runtime controls + read-only SQL console), served on its own thread by `python -m p2pwatch crawl`. A node is **two images, two containers**: the core `p2pwatch` (the crawler and its webui only, no s6, run as `PUID:PGID`, restarted by Docker) and `p2pwatch-amule`, compose service `ed2k`, where s6 supervises amuled (which starts amuleapi itself) and port-sync. The core reaches amuleapi at `ed2k:4711` in both compose variants (see the confinement invariant below).

## Orientation: read before substantial work

The live state, history, and recommended next step are deliberately **not** in this file (they would rot here). They live in:

- `agents/handoffs/`: one continuation guide per lot (`<ISO date> - handoff - <context>.md`). **The newest is the entry point**: current state, what was just built, learned pitfalls, next step, and what is *not yet validated against real hardware*.
- `agents/workflow.md`: how work moves (tiers, phases, the stacked blocks, pull request bodies, Wrap, defect classes, evidence, review findings). **Read it before starting a lot or a block.**
- `agents/specs/2026-06-10-crawler-mvp-design.md`: the authoritative MVP design (17 sections). Other dated specs in that dir record each subsystem's design + decisions; `agents/plans/` is historical, no plan is written since a tier Spec lot's spec is its brief.
- `docs/contributing/testing.md`: every test suite (unit + the integration markers), prerequisites, CI pistes.
- `docs/install.md`: bring a node up (the include layout and its direct/vpn variants, secrets, first boot); `docs/operate.md`: operate & tune one (lifecycle, metrics, catalog tools); `docs/high-id.md`, `docs/limits.md`, `docs/migration-4x.md` (4.x single container to the two-container layout); `docs/troubleshooting.md`: symptom → cause → fix entries (any level).
- `agents/reference/`: dated empirical findings about amuled. The EC notes there are a historical record since the 2026-09-22 migration to amuleapi; the live API reference is aMule's own `docs/api/REFERENCE.md`, in the source tree the image builds from.
- `BACKLOG.md` (repo root): what the project intends to do next, one entry of at most two lines each, linking the spec that holds the detail. **Read it before proposing work**, and write to it only after the operator has agreed. It carries no history: an entry is deleted when it ships or is dropped, never annotated. What reaches it (defect class 3, a review finding's exit) is in `agents/workflow.md`.
- `git tag`: releases are annotated `vX.Y.Z`, **pushed**, with the milestone name in the tag MESSAGE (`v1.0.1 - performance patch`), not in the tag itself. Pushing the tag is what publishes the versioned image: `release.yml` triggers on `v*`, publishing `X.Y.Z` **and** `latest`, then the GitHub release (title and notes from the tag message). Every push to `main` publishes `main`/`sha-<short>` and nothing else: `latest` means the newest release, never the tip of `main`, so an unreleased build is tested through the `main` tag. A release is the operator's decision, which the lead proposes after a lot's stack merges (`agents/workflow.md`, Wrap).

### Where the code lives

The crawler is Clean/Hexagonal (Hard rules): `domain/` pure, `ports/` its driving and driven ports, `application/` async use-cases, `adapters/` I/O, `composition/` wiring (`CrawlerApp`), the command line in `adapters/driving/cli/` (`python -m p2pwatch crawl`, `validate-config`, `merge`). Paths below are under `packages/crawler/src/p2pwatch/` (**c:**) unless noted.

| Subsystem | Location | Role |
|---|---|---|
| Matching engine | `packages/matching/src/catalog_matching/domain/` | declarative YAML-policy file→episode matcher (architecture: `packages/matching/AGENTS.md`), shared by the crawler and the in-process webui |
| WebUI (in-process) | c: `adapters/driving/webui/` | read-only catalog viewer (files, and the source history: `/sources`, a source's page `/sources/{source_id}`, a name's page `/sources/name`) + client status and runtime controls on the dashboard (`/`) + read-only SQL console (`/console`); Starlette/Jinja2 served on its own thread by `python -m p2pwatch crawl`; the bind is FIXED at `0.0.0.0:8080` in the root `__main__.py`, `crawler.yml`'s `webui.enabled` only gates the whole surface |
| amuleapi adapter | c: `adapters/driven/mule_api/` | REST client / JSON mapping / error contract for amuled (no probe tool: `curl` and amuleapi's own web UI replace them) |
| Persistence | c: `adapters/driven/persistence_sqlite/` | catalog.db, append-only, every table; local.db; `.sql` migrations; sync repos |
| Search / crawl loop | c: `domain/search/`, `application/` | keywords/backoff; one search task per (client, channel, keyword), persisted backoff |
| Download | c: `domain/download/` + ports/adapters | candidate → eD2k link → amuled queue → completion. Nothing moves or opens the file |
| Observability | c: `domain/observability/`, `adapters/driven/observability/` | events → policy → dispatcher; Prometheus + apprise |
| Port-sync (High-ID) | `packages/amule/src/p2pwatch_amule/adapters/driving/port_sync.py` | s6 service `port-sync` in the aMule container: gluetun's forwarded port → `s6-svc -wD -d` amuled → `amule.conf` `Port` + `UDPPort` → always `s6-svc -u`. Logs only, no event or metric; the core knows nothing of it (`port_sync:` is refused in `crawler.yml`) |
| Catalog merge | c: `application/merge_catalogs.py`, `adapters/driven/persistence_sqlite/sqlite_catalog_copier.py` | `python -m p2pwatch merge`: N→1 fusion, the use case `MergeCatalogs` over a `CatalogFinder` and a `CatalogCopier` |
| Container boot | `packages/amule/src/p2pwatch_amule/adapters/driving/boot.py` | `python -m p2pwatch_amule boot`, run once as root by the aMule image's entrypoint before s6: `amule` user, mount point ownership, amule.conf reconciled, amuleapi admin pass, port-sync's variables validated and its `down` file. Never imported by the crawler |
| Packaging | `deploy/compose.yml` (the core + one `include:`) + `deploy/ed2k/{service,direct,vpn}.compose.yml`, `tests/smoke/compose.yaml`, `packages/crawler/Dockerfile`, `packages/amule/Dockerfile` | two images: the core (Python + venv, `CMD python -m p2pwatch crawl`) and `p2pwatch-amule` (aMule build, s6, boot step, port-sync); the include line picks `direct` or `vpn` (`ed2k-gluetun` carries the alias `ed2k`), no compose profile; smoke stack on both images. aMule is built on Debian from the git commit pinned by `ARG AMULE_VERSION` + `ARG AMULE_COMMIT` in `packages/amule/Dockerfile` (bumped weekly by `.github/workflows/amule-bump.yml`); never write its version anywhere else |
| Supply-chain artefacts | `security/` + `.github/workflows/grype-scan.yml` + `release.yml` (`publish-manifest`) | one matrix leg per image: keyless cosign signature + 3 signed attestations (CycloneDX/Syft-JSON SBOM, OpenVEX) on each image's multi-arch index, one VEX per image (`security/{crawler,amule}.vex.openvex.json`); daily Grype scan of both → Code scanning. See `SECURITY.md`. |

## Design invariants (do not violate)

- **The catalog records files and, where a protocol publishes one, the pseudonymous identifier of the source that shared them**, so that a researcher can recognise a recurring sharer and contact a possible archivist. It never stores a peer's network address (IP, port, country), and never links identifiers across networks.
- **The crawler never reads downloaded bytes, and never touches the filesystem of the output directory.** The core mounts the output directory read-only, for the disk floor's `statvfs` only. One deliberate exception, in the aMule container: its boot step (`python -m p2pwatch_amule boot`) creates the mount points `/downloads/incoming` and `/downloads/temp` and chowns them, not recursively, to `PUID:PGID`, so that amuled, running as `amule`, can write there. It runs once as root before s6 starts anything, the crawler never imports it, and it never lists, opens or changes what the mounts contain. It lives in `packages/amule/`, under the same gate (mypy, coverage, the VEX source claims check).
- **`docs/` is the Zensical root and is published in full**: every `.md` under it becomes a page on https://mission-titar.github.io/p2pwatch/, because Zensical builds every file in `docs_dir` whether or not the nav references it. Anything that should not be published goes in `agents/` (specs, plans, handoffs, reference notes), never in `docs/`. The site is built by `uv run poe docs-build`, which passes `--strict` so a broken link or a dead anchor fails the build instead of shipping silently.
- **Package boundary:** which package imports which is the hexagon rule's (Hard rules, "Clean / Hexagonal"). `vex_checks`, `template_checks`, `coverage_checks` and `amule_bump` are dev/CI tooling, never installed in the prod image. `p2pwatch_testing` is imported only by the crawler's tests, whose `dev` group declares it, and is never installed in the prod image either.
- **Two run modes, one topology:** `download.enabled: true` (the shipped default) wires the download loop live; `download.enabled: false` or an absent `download:` section is crawl-only. This is a **config flag**, not two ways of assembling the stack: both compose variants start every service unconditionally, and there is no compose profile anywhere.
- **The merge** (`python -m p2pwatch merge`) is never called by the crawl and writes only to its destination: a new file (`--output`), or the source named by `--into`, which `open_catalog` first migrates in place to the current schema.
- **`deploy/` is the operator-owned single source of truth for config**: `deploy/crawler.yml` / `deploy/matcher.yml` / `deploy/targets.yml` stay editable-by-operator deployment config, next to the compose files that mount them; it is **forbidden to canonicalize them as code artifacts** (package data, inline policy dicts, or duplicate test fixtures that shadow them). Every consumer *derives from* `deploy/`, never the reverse: the matcher policy has exactly ONE copy (`deploy/matcher.yml`), read by the matching golden corpus + engine unit tests via `parents[N]`: a test-time path coupling to `deploy/`, deliberately accepted (test-only, not an import; the code DAG is unchanged). Do not reintroduce a `canonical_config.yaml` fixture or an inline `_CANONICAL_RAW` policy dict.
- **Boundary discipline** absorb failures from external I/O (an apprise notifier, a call to the daemon → degrade), but let in-process 100%-tested code crash loudly (a `PrometheusSink` failure is a bug, not a transient).
- **Persistence has no clock**: a repository stores the instants it is given and decides no wait; the use-case reads `wall_clock.now()` right before each write. An adapter other than persistence may hold a `MonotonicClock` for a guard of its own I/O: the amuleapi client's start pacing and search deadlines, the SQL console's query budget.

## Commands

The gate lives in `pyproject.toml` under `[tool.poe.tasks]` (poethepoet) as the single source of truth: the pre-push hook and CI both call it. `uv run poe` lists every task with its `help`.

```bash
uv sync --dev        # install (scripts/setup-dev.sh also installs the pre-push hook)
uv run poe check     # THE FULL GATE (lint-all + test): the pre-push hook and CI run exactly this
uv run poe fix       # auto-fix everything mechanical: ruff --fix + ruff format + sqlfluff fix
```

Gate sub-tasks, runnable in isolation: `lint` · `format-check` · `dependency-check` · `code-pattern-check` · `architecture-check` · `dead-code-check` · `type-check` · `sql-lint` · `template-check` (grouped as **`lint-all`**; `dependency-check` runs deptry twice per package, `src` against the runtime dependencies, then `src` and `tests` with the `dev` group too, `p2pwatch_testing` once since it has no tests; `code-pattern-check` runs the rule tests of `ast-grep-tests/`, then the ast-grep rules of `ast-grep-rules/` (their shared matcher in `ast-grep-utils/`), which `sgconfig.yml` names; `architecture-check` runs `tach check`, then `tach check-external`, over `tach.toml`; `dead-code-check` runs vulture once over every package's `src` but `p2pwatch_testing`'s, never the tests, ignoring the names the templates read, which poe passes it, so a bare `vulture` reports every view field; `type-check` runs mypy once per package, over its `src` and `tests`, so a `py.typed` package's errors show only in its own run), and **`test`** (runs each package's suite in its own process, so per-package coverage stays isolated, then `_unit-coverage-check`, which reads the per-test contexts each run records, `--cov-context=test`, and which poe runs only inside `test`, so it never reads a stale or partial `.coverage`). Fixers: `lint-fix` · `format-fix` · `sql-fix` (grouped as **`fix`**).

**Before hand-fixing lint / formatting / SQL, run `uv run poe fix`**: don't spend turns rewriting by hand what a fixer applies mechanically; review its diff instead.

**The gate is PER PACKAGE** (`cd packages/<pkg> && uv run pytest`). The intent: each package owns its own pytest config and 100 % branch coverage in isolation: a root run would mix coverage data across packages and break the per-package threshold. A bare `uv run pytest` from the repo root is also blocked mechanically (the root has no `[tool.pytest.ini_options]` and a root `conftest.py` sets `collect_ignore_glob = ["packages/*"]` → exit 5 with zero collected). Tooling split: `[tool.ruff]` at root spans all eight packages, `[tool.vulture]` and `tach.toml` all but `p2pwatch_testing`, and `[tool.mypy]` at root holds the settings every package's own run reads; `[tool.pytest]` / `[tool.coverage]` / `[tool.coverage_checks]` / `[tool.sqlfluff]` / `[tool.deptry]` are per-package, and so are the test dependencies, in each package's `dev` group (the root's holds only the workspace's tools); one root `uv.lock`. Every `tests/` directory is a package (data directories such as matching's `tests/fixtures` aside), so a test module is `tests.<path>`, imports its helpers as such (`from tests.fakes import FakeRepoReader`), and may share its basename with a test module of another directory or package. The tests mirror `src`: `src/<pkg>/a/b.py` is tested by `tests/a/test_b.py`, and by `tests/a/test_b_<aspect>.py` when its tests split (a test file belongs to the longest module name it extends; `__main__.py` and `__init__.py` take `test_main` and `test_init`); `unit-coverage-check` fails on a test file that tests no module, unless its package lists it in `[tool.coverage_checks] tests_without_unit` with what it tests. The crawler's shared test support is the package `p2pwatch_testing` (`from p2pwatch_testing.application.fakes import FakeTime`): it has no suite, the crawler's measures its coverage (`--cov=p2pwatch_testing`), so support code no test runs fails the crawler's gate. Deployment artifacts live under `deploy/` (`compose.yml`, the three config files, `.env.example`, `data/`, and `ed2k/` with its compose files and state); the smoke stack under `tests/smoke/`.

**Single test** (the package-wide `--cov-fail-under=100` makes a lone test "fail": disable coverage):

```bash
( cd packages/matching && uv run pytest tests/test_engine.py::test_evaluate_real_62a_is_download_via_first_rule_on_62a --no-cov -q )
```

Integration suites (Docker, deselected by default, excluded from coverage) are documented in `docs/contributing/testing.md`. They run locally, Docker Desktop included; only the compose smoke's completion test fails under Docker Desktop (its bind mount keeps SQLite's `-shm` incoherent), and CI is authoritative for it.

## Hard rules (enforced, non-negotiable: do not relax)

- **100% branch coverage on unit tests, per package, and of each module by its own tests**, gated in CI and the pre-push hook (`--cov-fail-under=100`, `branch=true`, and `test`'s `_unit-coverage-check`, where what a module's import runs counts as covered by any test). Integration suites (`api_integration`, `download_integration`, `orchestration_integration`, `compose_integration`) are deselected by the per-package `addopts` and excluded from coverage measurement: they run **on demand**, not in the gate (see `docs/contributing/testing.md`). Never lower the unit-test threshold; add the missing test (exercise *both* sides of every conditional).
- **Strict TDD**: tests are the spec; write the failing test first, watch it fail, then the minimal implementation. Code review judges the tests first. Every test function is annotated `-> None` with typed params.
- **`mypy --strict`** over **both `src` and `tests`**. **`ruff`** selects `E,F,I,UP,B,SIM,TID251`, line-length **100**.
- **No dynamic attribute access**: `getattr`, `setattr`, `hasattr`, `delattr` and `vars` are banned in `src` and `tests`, and so are `__dict__`, `__getattribute__`, `__setattr__`, `__delattr__`, `operator.attrgetter` and `operator.methodcaller`, even as an attribute's or a method's name (`code-pattern-check`, which refuses `__builtins__` and any import of `builtins` too, so `builtins.getattr` cannot be written out). An exception carries `# ast-grep-ignore: no-dynamic-attribute` and its reason.
- **No code only tests reach**: `dead-code-check` reports what no production path uses: delete it with its tests. `vulture_whitelist.py` is a rare exit for a blind tool: first make the call visible to vulture (pass a hook by name, e.g. a function as `BaseHTTPMiddleware(dispatch=...)`); an entry only for a call no rewrite can show, with its reason. A name a template reads needs nothing.
- **Only the clock adapters read the system clock, asyncio's own timeouts aside**: everything else injects `WallClock` or `MonotonicClock`. `TID251` bans the calls (`datetime.now`, `time.monotonic`, `asyncio.sleep`…) outside `SystemWallClock`, `AsyncioMonotonicClock`, every `tests/` tree, `packages/crawler_testing/` and `packages/amule/`; it leaves `asyncio.wait_for` and `asyncio.timeout` allowed and cannot see `loop.time()`, all three on the event loop's monotonic time. A yield, `asyncio.sleep(0)`, keeps a `# noqa: TID251`.
- **Clean / Hexagonal** (`agents/specs/2026-10-18-hexagonal-architecture.md`): six hexagons, `p2pwatch` (with `catalog_matching`, its domain ring in a distribution of its own), `p2pwatch_amule`, `vex_checks`, `template_checks`, `coverage_checks` and `amule_bump`, never import one another. The ring is read from the path, `<pkg>/{domain,ports,application,adapters,composition}/`, with `ports/` and `adapters/` split into `driving/` and `driven/`; a root `__main__.py` belongs to the composition. Imports point inward (`domain` < `ports` < `application` < `adapters` < `composition`) and form no cycle; an adapter never imports another adapter, a driving adapter depends on driving ports only, a driven adapter on the driven ports it implements or consumes, a use case implements a driving port over driven ports, and every one of them may import its domain.
- **No I/O in the core**: `domain/`, `ports/` and `application/` import only their ring's list in `ast-grep-rules/*-imports.yml` (the pure standard library they use, `rapidfuzz`, first-party packages), `asyncio`, `uuid` and `io` by the names `core-import-names.yml` lists, `pathlib` by `PurePath`, `configparser` in `p2pwatch_amule`'s domain only, and call no builtin that does I/O or imports (`core-builtins.yml`); the rules see imports and builtin calls, not what an allowed module's methods do; `logging` stays in `application/`'s list until lot 2 gives it a port. A module that does I/O goes to an adapter, even if most of it is logic; where that would have the core import an adapter, the imported piece moves into the core. A new import is a new line in its ring's list, never an ignore. `${NAME}` env-var interpolation in `crawler.yml` is resolved by the config adapter before anything reaches the domain: the domain itself never touches env vars.
- **Every module is declared in `tach.toml`**, one per port file and per adapter, with exactly the dependencies it uses (`root_module = "forbid"`, `exact`): an undeclared module or edge fails `architecture-check`. A rule broken for now is a dependency declared `deprecated = true`, beside a comment naming its reason and the lot that removes it, never a `# tach-ignore`. `tach check` never sees an import across distributions: `tach check-external` holds each to its package's `pyproject.toml`, and `packages/crawler/tests/test_workspace_dependencies.py` refuses any internal dependency but `p2pwatch` on `catalog-matching` and on `p2pwatch-testing` (`dev`), and `p2pwatch-testing` on `p2pwatch`.
- **Python only** (>=3.13). Conventional commits (`feat(domain):`, `fix(domain):`, `test:`, `chore:`, `docs:`).
- **Language: all code is English** (decided 2026-07-02), identifiers AND prose: comments, docstrings, runtime-emitted messages/logs, CI step names, and commit messages. `.gitignore` and `.gitattributes` are the deliberate exceptions (`.gitignore` decided 2026-09-17): operator-facing housekeeping, consistently French. The only other French in the codebase is genuine *domain data* (real VF episode titles like `La Grenouille Cosmique`, eMule filenames, non-ASCII test fixtures): data, not prose. **New docs under `agents/specs/`, `agents/plans/` and `agents/handoffs/` are written in English** (decided 2026-07-03); past docs keep their original language (no retro-translation). **Everything under `docs/` is French** (decided 2026-09-17), contributor section included: `docs/` is the published documentation site and its readers are operators. Conversational replies to the operator stay in their chosen language.
- **One named teammate per block of a tier Spec lot** (Act) and **the holistic review once per tier Spec lot**, at the head of Wrap over the top of the stack (`agents/workflow.md`): the cross-cutting review regularly catches bugs, don't skip it. A lot of one block is offered its waiver and the operator decides; tier Direct has none.
- For library/framework/CLI questions, use the current docs, not recalled knowledge.

## Naming

A name lets a reader with partial context tell, from a signature or a call site, what a value holds and what
a function does.

- **One concept, one name, in every layer.** A value keeps its name from where it enters to where it is read.
  An external name (an amuleapi field, a SQLite function's) is translated once, in its mapper or adapter, and
  kept from there. The glossary below fixes the shared words.
- **One name, one concept, within a package**: never a string in one function and a dict under the same
  name in the next.
- **Say what the value is, not its type or its role**: no `what`, `data`, `info`, `item`, `obj`, `result`,
  `value`, `entry`, `payload`; a single letter only inside a one-line comprehension or lambda.
- **A quantity carries its unit unless its type does**: `_seconds`, `_bytes`, `_mib`, `_micros`; a `datetime`
  or a `timedelta` needs none.
- **A boolean reads as a predicate**: `is_tracked`, `has_useful_point`, `clamped`, `enabled`.
- **A function says what it returns or does, side effects included**: `get_or_create_node_id`,
  `rejudge_file`. A class names what one instance is.
- **A mapping is `<values>_by_<key>`, a collection the plural of its element.**
- **`latest` is the most recent of a series; `last` only pairs with `first`.**
- **No abbreviation but the glossary's**, units and protocol names (`kbps`, `tcp`, `md4`, `ed2k`) aside.
- **Comments, docstrings and log messages use the code's words.**
- **The most telling word wins over the most widespread one**: an existing name is not a reason to keep it.
- **A port is named after the one who does its action**: `CatalogMerger`, "the one who merges catalogs". New
  ports are ABCs.
- **A use case is named after its operation**: `ValidateConfig`, `MergeCatalogs`.
- **An adapter is named by its technology and what it adapts**: `PosixProcess`, `UvicornServerThread`,
  `YamlConfigChecker`, `SqliteCatalogCopier`.
- **A test double is `Fake` and what it replaces**: `FakeAmuleApiServer`, `FakeSearchClient`.

| Word | Means | Never |
|---|---|---|
| `network` | `Network`, a file identity's namespace; eD2k covers Kad | for `ed2k`/`kad`: that is a channel |
| `channel` | one search channel of a client: `ed2k`, `kad` | `network` |
| `connected` | a channel has joined its network (an eD2k server, the Kad DHT) | `on_network` |
| `connectable` | peers can open a connection to it: one of our channels, or a source | `directly_reachable`, `high_id` |
| `client` | a port object driving a P2P client; `client_name` is its configured label | `instance`, a bare `name` |
| `node` | one running p2pwatch, `node_id` | `instance` |
| `file` | a `FileKey`: `network` and `native_id` | a string |
| `native_id` | the network's own file id (MD4 on eD2k) | `ed2k_hash` past the mapper |
| `filename` | a file's name, a string: `latest_filename`, `best_filename`, `known_filenames` | `name`, `file_name` |
| `source` | a peer sharing a file, `SourceKey`; `source_name` its advertised name | a bare `name` beside a filename |
| `candidate` | a `FileCandidate`, one name of a file and its metadata, the matcher's input; a `DownloadCandidate` is a file with a download-tier decision | `names` |
| `target` | an episode segment to recover: `target_id`, `TargetSegment`, its `letter` | `segment` for the letter; Kad's keyword target, which is a `kad_word` |
| `tier` | a decision's strength: `catalog`, `notify`, `download` | `before`, `after` |
| `token` | a named matcher of the policy (`tokens:`) | a word of a text |
| `word` | a piece of normalized text | `token` |
| `reevaluation` | re-judging every file when the policy changed | `backfill` |
| `tracked` | a download with a row in `downloads`, whatever its state | `downloaded`, `active` |
| `wake` | `WakeHub` wakes the loops waiting on a subject | `signal`, `nudge` |
| `first useful`, `reappeared` | a source's two alerts | `new`, `useful again` |
| `audience` | who a notification is for: `community`, `operations` | `tag` (apprise's keyword aside), `channel` |
| `error_label` | the label a parser prints in its errors | `what`, `label`, `field` |
| `wall clock` | `WallClock`, the UTC time of day: every stamp a row, an event or a display carries | an interval or a deadline kept in memory |
| `monotonic clock` | `MonotonicClock`, its `MonotonicInstant`s: every interval and deadline kept in memory | a stamp, anything persisted |
| `persisted wait` | a wait that survives a restart: its start on the wall clock and its duration, clamped by `remaining_wait` when the node meets it again | a deadline persisted alone |
| `own tests` | a module's own tests: the test files named after it, in the directory mirroring its own (`tests/a/test_b*.py` for `src/<pkg>/a/b.py`) | a test that runs the module in passing |
| `ring` | one of a hexagon's concentric parts, read from the path: `domain`, `ports`, `application`, `adapters`, `composition` | `layer` |
| `hexagon` | one application, its core and its adapters, which never imports another hexagon; `p2pwatch` is one | a package |
| `driving` | the side that calls the core: a driving port is what a use case offers, a driving adapter calls it (the command line, the webui) | `primary`, `inbound` |
| `driven` | the side the core calls: a driven port is what the core needs, a driven adapter implements it (SQLite, amuleapi) | `secondary`, `outbound` |
| `use case` | an `application/` operation behind a driving port: `ValidateConfig` | `service`, `interactor` |
| `micros` | an integer of microseconds: an instant counts from the epoch | a bare `_at` on an `int` |
| `id`, `db`, `sql`, `url`, `api`, `json`, `ecid`, `mib`, `iso`, `min`, `max`, `conf` | the abbreviations allowed (`conf`: aMule's `amule.conf`) | |

## Workflow

Tiers, phases, blocks, the stack, pull requests, Wrap and review findings: `agents/workflow.md`.

## Gotchas

**Matching engine (stdlib `re`, `re.ASCII`):**
- Regex tokens compile with `re.compile(pattern, re.ASCII)` (`matchers.py`, `validation.py`). `re.ASCII` keeps `\b \d \s \w` ASCII: matching the pre-2026-07-03 RE2 default the existing policy relies on (`fold()` does not reduce non-Latin scripts to ASCII). Case-insensitivity is a leading `(?i)` prefix (not a flag arg). An invalid pattern raises **`re.error`** (caught in `validation.py` → `MatchingConfigError` "not compilable").
- Coverage idioms: a `Protocol` stub `def m(...) -> bool: ...` must be **one line** (a body with `...` on a second line counts as an uncovered branch under `branch=true`). A `case _: assert_never(x)` arm (the "unreachable default" of a `match` over a closed tagged-union) needs `# pragma: no cover` because it is unreachable by design but the branch counter doesn't know that.
- Don't validate config order-dependently (parse pass = structural; graph pass = full table). Recursive validators need an explicit depth guard → a clean `DepthExceededError`, not `RecursionError` (which is a Python runtime artifact, not a domain error).

**Coverage by own tests (`_unit-coverage-check`):**
- **A body the process runs once is credited to one test at most.** A function called at import is credited to none (pytest-cov records collection under the empty context), so its module's own tests must call it. A `functools.cache`d function, module state initialised lazily, or a session- or module-scoped fixture is credited to whichever test runs it first, so its module's own tests pass or fail on test order and selection: keep such state out of `src`, or have the module's own tests reset it (`cache_clear()`).

**amuleapi / amuled (empirical: facts established by hardware probes / source reading, see `agents/reference/`):**
- *amuleapi = the daemon aMule (the version pinned by `ARG AMULE_VERSION` in `packages/amule/Dockerfile`) ships to expose amuled over `/api/v1/*` REST plus SSE, and to serve aMule's web UI. amuled starts it itself (`[AmuleApi] Enabled=1`) and hands it a one-off EC token; EC is now an internal link between the two, not something we speak.*
- **Every list endpoint silently returns only the first 100 rows.** `limit` defaults to 100 on `/downloads`, `/shared`, `/search/{id}/results` and every other list route, so omitting it returns the first hundred items, not the collection. For `downloads()` that is a silent completion failure on any node with more than a hundred queued or shared files. The adapter keyset-pages on the route's identity column (`sort=hash` + `after=<last hash>` for downloads and shared files, `sort=ecid` + `after=<last ecid>` for a download's clients), never `offset`, because `offset` is a position and a row deleted below the cursor slides one row past the window for good.
- **A `401` is terminal for the session.** amuleapi counts every rejected token per IP (30 in 60 s → a 300 s lockout), so a client that retries a `401` locks itself out. The adapter re-logs in exactly ONCE per request and never loops. Restarting amuleapi, or any password change, invalidates every issued token.
- **`media` on a search result is what the responding server advertised**, never a local probe: it can contradict the file (a `.pdf` reporting a runtime and a video codec is a real observed result), and it is `null` on most global and Kad hits. The key is always present, so test for `null`, not for the key.
- **amuled folds the same file's alternative filenames** into `alternate_names[]` under the most-sourced parent; only parents appear at the top level. The mapper unfolds them into one observation per name, because dropping them loses the descriptive name on a third of the catalog's multi-name hashes.
- amuled moves a finished file to its IncomingDir and flips status to complete **after** the move (no race), so by the time the completion is observable the file is already at its final on-disk path. Completion is the client's **positive signal**, never a byte count: a queue entry with `status == "completed"` (moved, awaiting clear), or a file in `GET /shared` and absent from the queue (completed then cleared). A queued file listed in `/shared` is not complete, since amuled shares partfiles too. Detail: `2026-06-17-amuled-completion-behavior.md`.
- **Two listen ports**: TCP `[eMule] Port` (4662) and UDP `[eMule] UDPPort` (4672, Kad's). The direct variant publishes `4672/udp`, never `4662/udp`; port-sync writes both to the one port a tunnel forwards. amuled reads them only at start, and flushes its whole config when it exits, so `amule.conf` is written only while amuled is down.
- **Neither password has a length minimum** in aMule at the pinned commit (no 12-character rule exists); the boot step refuses only control characters in them.

**Serena and its language server, pyrefly (sections cited from `agents/reference/2026-10-16-python-language-server-bench.md`):**
- **A port method is renamed from the port, then again from each implementer.** The ports are `Protocol`s, and no server links a structural implementation to its port (bench 11). Renamed from a base or an ABC, pyrefly reaches the overrides; renamed from an override, it never climbs to the base.
- **An override whose base comes from another test module is not renamed with its base** (`from tests.application.test_run_download_cycle import ...`): pyrefly does not resolve one `tests` package importing another, and mypy stays green, since the stale override becomes an extra method (bench 11).
- **Never renamed completely by any server**: a pytest fixture's uses in the test bodies, an attribute only a Jinja template reads, a name inside a string (`__all__` included, under pyrefly) and a `dataclasses.replace` keyword (bench 3.1, 5.7).
- **`.serena/project.yml` pins pyrefly 1.4.0 in `lazy-blocking` mode only in a project Serena trusts** (`trusted_project_path_patterns` in the user's global Serena config). Untrusted, Serena starts its own pyrefly 1.2.0 in the default mode, whose first rename after start is partial (bench 11).
