# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`p2pwatch` continuously surveils the eMule network (eD2k + Kad, via an aMule client driven over amuleapi, its REST surface) to recover lost-media episodes of the French dub of *Keroro mission Titar* (aired 2008 on Teletoon), cataloguing all available metadata along the way.

It is a **virtual uv workspace** with six packages: `packages/crawler/` (package `p2pwatch`, dist `p2pwatch`), `packages/amule/` (package `p2pwatch_amule`, dist `p2pwatch-amule`, stdlib only, the aMule container's boot step and port-sync), `packages/matching/` (package `catalog_matching`, dist `catalog-matching`, shared domain), and three dev/CI tooling packages never shipped in a prod image: `packages/vex_checks/` (package `vex_checks`, dist `vex-checks`, reads `security/*.vex.openvex.json` to keep our OpenVEX claims honest), `packages/template_checks/` (package `template_checks`, dist `template-checks`, stdlib only, keeps the webui's Jinja templates logic-free: `poe template-check`) and `packages/amule_bump/` (package `amule_bump`, dist `amule-bump`, stdlib only, run by `.github/workflows/amule-bump.yml` to bump the aMule pin and write the PR body). The crawler package `p2pwatch` also contains the in-process webui subpackage `p2pwatch.webui` (read-only catalog viewer + light runtime controls + read-only SQL console), served on its own thread by `python -m p2pwatch`. A node is **two images, two containers**: the core `p2pwatch` (the crawler and its webui only, no s6, run as `PUID:PGID`, restarted by Docker) and `p2pwatch-amule`, compose service `ed2k`, where s6 supervises amuled (which starts amuleapi itself) and port-sync. The core reaches amuleapi at `ed2k:4711` in both compose variants (see the confinement invariant below).

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

The crawler is Clean/Hexagonal: `domain/` pure, `application/` async use-cases, `adapters/` I/O, `composition/` wiring (`CrawlerApp` + `python -m p2pwatch`). Paths below are under `packages/crawler/src/p2pwatch/` (**c:**) unless noted.

| Subsystem | Location | Role |
|---|---|---|
| Matching engine | `packages/matching/src/catalog_matching/` | declarative YAML-policy file→episode matcher (architecture: `packages/matching/AGENTS.md`), shared by the crawler and the in-process webui |
| WebUI (in-process) | c: `webui/` | read-only catalog viewer (files, and the source history: `/sources`, a source's page `/sources/{source_id}`, a name's page `/sources/name`) + client status and runtime controls on the dashboard (`/`) + read-only SQL console (`/console`); Starlette/Jinja2 served on its own thread by `python -m p2pwatch`; the bind is FIXED at `0.0.0.0:8080` in code, `crawler.yml`'s `webui.enabled` only gates the whole surface |
| amuleapi adapter | c: `adapters/mule_api/` | REST client / JSON mapping / error contract for amuled (no probe tool: `curl` and amuleapi's own web UI replace them) |
| Persistence | c: `adapters/persistence_sqlite/` | catalog.db, append-only, every table; local.db; `.sql` migrations; sync repos |
| Search / crawl loop | c: `domain/search/`, `application/` | keywords/backoff; one search task per (client, channel, keyword), persisted backoff |
| Download | c: `domain/download/` + ports/adapters | candidate → eD2k link → amuled queue → completion. Nothing moves or opens the file |
| Observability | c: `domain/observability/`, `adapters/observability/` | events → policy → dispatcher; Prometheus + apprise |
| Port-sync (High-ID) | `packages/amule/src/p2pwatch_amule/port_sync/` | s6 service `port-sync` in the aMule container: gluetun's forwarded port → `s6-svc -wD -d` amuled → `amule.conf` `Port` + `UDPPort` → always `s6-svc -u`. Logs only, no event or metric; the core knows nothing of it (`port_sync:` is refused in `crawler.yml`) |
| Standalone catalog tool | c: `merge/` | `python -m p2pwatch.merge`: N→1 fusion |
| Container boot | `packages/amule/src/p2pwatch_amule/boot/` | `python -m p2pwatch_amule.boot`, run once as root by the aMule image's entrypoint before s6: `amule` user, mount point ownership, amule.conf reconciled, amuleapi admin pass, port-sync's variables validated and its `down` file. Never imported by the crawler |
| Packaging | `deploy/compose.yml` (the core + one `include:`) + `deploy/ed2k/{service,direct,vpn}.compose.yml`, `tests/smoke/compose.yaml`, `packages/crawler/Dockerfile`, `packages/amule/Dockerfile` | two images: the core (Python + venv, `CMD python -m p2pwatch`) and `p2pwatch-amule` (aMule build, s6, boot step, port-sync); the include line picks `direct` or `vpn` (`ed2k-gluetun` carries the alias `ed2k`), no compose profile; smoke stack on both images. aMule is built on Debian from the git commit pinned by `ARG AMULE_VERSION` + `ARG AMULE_COMMIT` in `packages/amule/Dockerfile` (bumped weekly by `.github/workflows/amule-bump.yml`); never write its version anywhere else |
| Supply-chain artefacts | `security/` + `.github/workflows/grype-scan.yml` + `release.yml` (`publish-manifest`) | one matrix leg per image: keyless cosign signature + 3 signed attestations (CycloneDX/Syft-JSON SBOM, OpenVEX) on each image's multi-arch index, one VEX per image (`security/{crawler,amule}.vex.openvex.json`); daily Grype scan of both → Code scanning. See `SECURITY.md`. |

## Design invariants (do not violate)

- **The catalog records files and, where a protocol publishes one, the pseudonymous identifier of the source that shared them**, so that a researcher can recognise a recurring sharer and contact a possible archivist. It never stores a peer's network address (IP, port, country), and never links identifiers across networks.
- **The crawler never reads downloaded bytes, and never touches the filesystem of the output directory.** The core mounts the output directory read-only, for the disk floor's `statvfs` only. One deliberate exception, in the aMule container: its boot step `p2pwatch_amule.boot` creates the mount points `/downloads/incoming` and `/downloads/temp` and chowns them, not recursively, to `PUID:PGID`, so that amuled, running as `amule`, can write there. It runs once as root before s6 starts anything, the crawler never imports it, and it never lists, opens or changes what the mounts contain. It lives in `packages/amule/`, under the same gate (mypy, coverage, the VEX source claims check).
- **`docs/` is the Zensical root and is published in full**: every `.md` under it becomes a page on https://mission-titar.github.io/p2pwatch/, because Zensical builds every file in `docs_dir` whether or not the nav references it. Anything that should not be published goes in `agents/` (specs, plans, handoffs, reference notes), never in `docs/`. The site is built by `uv run poe docs-build`, which passes `--strict` so a broken link or a dead anchor fails the build instead of shipping silently.
- **Package boundary:** `catalog_matching` is a pure shared library imported by the crawler (and by its in-process webui), never the reverse. `p2pwatch_amule` never imports the crawler, nor the crawler it. `vex_checks`, `template_checks` and `amule_bump` are dev/CI tooling: never imported by shipped code, nor installed in the prod image.
- **Two run modes, one topology:** `download.enabled: true` (the shipped default) wires the download loop live; `download.enabled: false` or an absent `download:` section is crawl-only. This is a **config flag**, not two ways of assembling the stack: both compose variants start every service unconditionally, and there is no compose profile anywhere.
- **The standalone tool** (`merge`) is never imported by the crawler and writes only to its destination: a new file (`--output`), or the source named by `--into`, which `open_catalog` first migrates in place to the current schema.
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

Gate sub-tasks, runnable in isolation: `lint` · `format-check` · `dependency-check` · `code-pattern-check` · `type-check` · `sql-lint` · `template-check` (grouped as **`lint-all`**; `dependency-check` runs deptry twice per package, `src` against the runtime dependencies, then `src` and `tests` with the `dev` group too; `code-pattern-check` runs the ast-grep rules of `ast-grep-rules/`, which `sgconfig.yml` names), and **`test`** (runs each package's suite in its own process, so per-package coverage stays isolated). Fixers: `lint-fix` · `format-fix` · `sql-fix` (grouped as **`fix`**).

**Before hand-fixing lint / formatting / SQL, run `uv run poe fix`**: don't spend turns rewriting by hand what a fixer applies mechanically; review its diff instead.

**The gate is PER PACKAGE** (`cd packages/<pkg> && uv run pytest`). The intent: each package owns its own pytest config and 100 % branch coverage in isolation: a root run would mix coverage data across packages and break the per-package threshold. A bare `uv run pytest` from the repo root is also blocked mechanically (the root has no `[tool.pytest.ini_options]` and a root `conftest.py` sets `collect_ignore_glob = ["packages/*"]` → exit 5 with zero collected). Tooling split: `[tool.ruff]` / `[tool.mypy]` at root span all six packages; `[tool.pytest]` / `[tool.coverage]` / `[tool.sqlfluff]` / `[tool.deptry]` are per-package, and so are the test dependencies, in each package's `dev` group (the root's holds only the workspace's tools); one root `uv.lock`. Deployment artifacts live under `deploy/` (`compose.yml`, the three config files, `.env.example`, `data/`, and `ed2k/` with its compose files and state); the smoke stack under `tests/smoke/`.

**Single test** (the package-wide `--cov-fail-under=100` makes a lone test "fail": disable coverage):

```bash
( cd packages/matching && uv run pytest tests/test_engine.py::test_evaluate_real_62a_is_download_via_first_rule_on_62a --no-cov -q )
```

Integration suites (Docker, deselected by default, excluded from coverage) are documented in `docs/contributing/testing.md`. They run locally, Docker Desktop included; only the compose smoke's completion test fails under Docker Desktop (its bind mount keeps SQLite's `-shm` incoherent), and CI is authoritative for it.

## Hard rules (enforced, non-negotiable: do not relax)

- **100% branch coverage on unit tests, per package**, gated in CI and the pre-push hook (`--cov-fail-under=100`, `branch=true`). Integration suites (`api_integration`, `download_integration`, `orchestration_integration`, `compose_integration`) are deselected by the per-package `addopts` and excluded from coverage measurement: they run **on demand**, not in the gate (see `docs/contributing/testing.md`). Never lower the unit-test threshold; add the missing test (exercise *both* sides of every conditional).
- **Strict TDD**: tests are the spec; write the failing test first, watch it fail, then the minimal implementation. Code review judges the tests first. Every test function is annotated `-> None` with typed params.
- **`mypy --strict`** over **both `src` and `tests`**. **`ruff`** selects `E,F,I,UP,B,SIM,TID251`, line-length **100**.
- **No dynamic attribute access**: `getattr`, `setattr`, `hasattr` and `delattr` are banned in `src` and `tests` (`code-pattern-check`, which refuses `__builtins__` and any import of `builtins` too, so `builtins.getattr` cannot be written out). An exception carries `# ast-grep-ignore: no-dynamic-attribute` and its reason.
- **Only the clock adapters read the system clock, asyncio's own timeouts aside**: everything else injects `WallClock` or `MonotonicClock`. `TID251` bans the calls (`datetime.now`, `time.monotonic`, `asyncio.sleep`…) outside `SystemWallClock`, `AsyncioMonotonicClock`, every `tests/` tree and `packages/amule/`; it leaves `asyncio.wait_for` and `asyncio.timeout` allowed and cannot see `loop.time()`, all three on the event loop's monotonic time. A yield, `asyncio.sleep(0)`, keeps a `# noqa: TID251`.
- **Clean / Hexagonal**: `domain/` is **pure**: no I/O, no `yaml`/DB/network/clock/logging imports. All I/O lives in `adapters/`. The dependency graph is a DAG. `${NAME}` env-var interpolation in `crawler.yml` is resolved by the config adapter before anything reaches the domain: the domain itself never touches env vars.
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
| `micros` | an integer of microseconds: an instant counts from the epoch | a bare `_at` on an `int` |
| `id`, `db`, `sql`, `url`, `api`, `json`, `ecid`, `mib`, `iso`, `min`, `max`, `conf` | the abbreviations allowed (`conf`: aMule's `amule.conf`) | |

## Workflow

Tiers, phases, blocks, the stack, pull requests, Wrap and review findings: `agents/workflow.md`.

## Gotchas

**Matching engine (stdlib `re`, `re.ASCII`):**
- Regex tokens compile with `re.compile(pattern, re.ASCII)` (`matchers.py`, `validation.py`). `re.ASCII` keeps `\b \d \s \w` ASCII: matching the pre-2026-07-03 RE2 default the existing policy relies on (`fold()` does not reduce non-Latin scripts to ASCII). Case-insensitivity is a leading `(?i)` prefix (not a flag arg). An invalid pattern raises **`re.error`** (caught in `validation.py` → `MatchingConfigError` "not compilable").
- Coverage idioms: a `Protocol` stub `def m(...) -> bool: ...` must be **one line** (a body with `...` on a second line counts as an uncovered branch under `branch=true`). A `case _: assert_never(x)` arm (the "unreachable default" of a `match` over a closed tagged-union) needs `# pragma: no cover` because it is unreachable by design but the branch counter doesn't know that.
- Don't validate config order-dependently (parse pass = structural; graph pass = full table). Recursive validators need an explicit depth guard → a clean `DepthExceededError`, not `RecursionError` (which is a Python runtime artifact, not a domain error).

**amuleapi / amuled (empirical: facts established by hardware probes / source reading, see `agents/reference/`):**
- *amuleapi = the daemon aMule (the version pinned by `ARG AMULE_VERSION` in `packages/amule/Dockerfile`) ships to expose amuled over `/api/v1/*` REST plus SSE, and to serve aMule's web UI. amuled starts it itself (`[AmuleApi] Enabled=1`) and hands it a one-off EC token; EC is now an internal link between the two, not something we speak.*
- **Every list endpoint silently returns only the first 100 rows.** `limit` defaults to 100 on `/downloads`, `/shared`, `/search/{id}/results` and every other list route, so omitting it returns the first hundred items, not the collection. For `downloads()` that is a silent completion failure on any node with more than a hundred queued or shared files. The adapter keyset-pages on the route's identity column (`sort=hash` + `after=<last hash>` for downloads and shared files, `sort=ecid` + `after=<last ecid>` for a download's clients), never `offset`, because `offset` is a position and a row deleted below the cursor slides one row past the window for good.
- **A `401` is terminal for the session.** amuleapi counts every rejected token per IP (30 in 60 s → a 300 s lockout), so a client that retries a `401` locks itself out. The adapter re-logs in exactly ONCE per request and never loops. Restarting amuleapi, or any password change, invalidates every issued token.
- **`media` on a search result is what the responding server advertised**, never a local probe: it can contradict the file (a `.pdf` reporting a runtime and a video codec is a real observed result), and it is `null` on most global and Kad hits. The key is always present, so test for `null`, not for the key.
- **amuled folds the same file's alternative filenames** into `alternate_names[]` under the most-sourced parent; only parents appear at the top level. The mapper unfolds them into one observation per name, because dropping them loses the descriptive name on a third of the catalog's multi-name hashes.
- amuled moves a finished file to its IncomingDir and flips status to complete **after** the move (no race), so by the time the completion is observable the file is already at its final on-disk path. Completion is the client's **positive signal**, never a byte count: a queue entry with `status == "completed"` (moved, awaiting clear), or a file in `GET /shared` and absent from the queue (completed then cleared). A queued file listed in `/shared` is not complete, since amuled shares partfiles too. Detail: `2026-06-17-amuled-completion-behavior.md`.
- **Two listen ports**: TCP `[eMule] Port` (4662) and UDP `[eMule] UDPPort` (4672, Kad's). The direct variant publishes `4672/udp`, never `4662/udp`; port-sync writes both to the one port a tunnel forwards. amuled reads them only at start, and flushes its whole config when it exits, so `amule.conf` is written only while amuled is down.
- **Neither password has a length minimum** in aMule at the pinned commit (no 12-character rule exists); the boot step refuses only control characters in them.
