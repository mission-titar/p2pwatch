# v5 release readiness

Status: umbrella spec of the seven lots that precede v5.0.0, settled in Discuss with the operator on 2026-11-04 from
a six-teammate audit of `v4.1.0..main` (`main` at `fc8c9eae`). Each lot gets its own spec, which cites this one for
the decisions already taken and re-runs every measurement before acting on it. Approved by the operator on
2026-11-04 and committed to `main` directly, as a document touching `agents/` only. The decisions are the operator's; their reasons are those given in the discussion, the lead's included
where the operator accepted a recommendation.

## In short

v5 is the first release since v4.1.0: 1 010 commits, the rename to p2pwatch, aMule in its own container, and many
breaking changes to the configuration and both databases. The audit proved the data side sound: a full-scale
migration of a copy of the operator's node kept every observation, decision and download, and the matching engine
decides exactly as v4 did on every file of the real catalog. It also found two blockers: the migration guide,
followed literally, leaves the operator's node in a restart loop, and under the VPN a port change cuts the crawler
off from aMule for good. Twelve major and thirty-eight minor defects complete the list (appendix A).

The operator wants the upgrade as simple as possible and the code without bugs. v5 therefore ships after seven lots,
each holding one theme a reviewer reads in one sitting, rather than a cut sized to the 19-block bound; then through
one or more release candidates tested on the operator's own node.

## What the operator sees at v5.0.0

- **The upgrade guide works when followed literally**, says what to carry over from the old compose files, and has
  the operator stop the node before backing it up.
- **One validation run names every configuration problem at once**, across the three files.
- **The first start says what it does** in its log, and an interrupted upgrade restarts without a second copy.
- **Under the VPN, a new forwarded port is applied live**: aMule is never restarted for it.
- **A bug in one part of the crawler no longer stops the whole node.**
- **The Node page can abandon or retry a download**: no procedure asks for a hand edit of `local.db` any more.
- **A release candidate is a prerelease**: it never becomes `latest`.

## Decisions

### Lot 1: the aMule container

- **D1. The port-sync changes amuled's ports live through amuleapi, and never restarts amuled.** *A restart lets the
  new amuleapi start while the old one still holds its port, so it exits without an error and aMule never relaunches
  it; changing the ports live removes that trigger, and with it the image's restart machinery.* That the live change
  keeps High-ID behind a real forwarding VPN is unproven offline; it is checked on the operator's node at the first
  rc. Should it fail, the fallback is designed in lot 1: the port-sync writes the new port and exits, so Docker
  restarts the container on it (D24) (Corrected: lot 1's D2 and D3: the fallback is described there, not written, and the
  container restarts through s6's `finish`, D24 replaced).
- **D24. s6 leaves the aMule image: its entrypoint starts amuled and the port-sync, stops the other as soon as one
  exits, and exits in error, so Docker restarts the container.** *With the live port change, s6's only remaining role
  is to run two processes and restart the one that dies; a container restart does it with less code, removes the
  port race by construction (every process dies before the new ones start), and gives both containers one model:
  Docker is the only supervisor.* The cost, accepted: a port-sync bug restarts amuled too, which reconnects to eD2k
  and Kad; it shows in the container's restart count, and lot 4 makes the port-sync robust to its own errors. (Corrected: replaced by lot 1's D3, s6 kept with a
  `finish` per service that brings the container down, exit 0; `agents/specs/2026-11-04-v5-amule-container.md`.)
- **D2. The ed2k healthcheck also requires amuleapi to answer.** *Today it checks amuled alone, so a container whose
  crawler has lost aMule reports `healthy`.*

### Lot 2: the migration and the first start

- **D4. One upgrade, one copy: the migrations of one start run all or nothing**, and the free-space check counts the
  larger journal that one block writes, measured on the real catalog. *Today each migration commits on its own, so a
  stop mid-way leaves an intermediate version and the restart writes a second full copy that no release can read,
  enough to refuse a node whose disk is sized as the docs say; a refusal must come before the copy, never in the
  middle of the block.* (Corrected: an out-of-space during the block refuses after the copy, rolled back whole, lot 2's D1.)
- **D5. The final space reclaim (`VACUUM`) runs after that block, takes no copy, and runs again at the next start if
  it was interrupted.** *SQLite refuses it inside a transaction, and an interrupted one leaves the database intact
  but still oversized.*
- **D6. The first start says what it does in the log**: before the copy, its size, the expected wait and not to
  restart; progress during the copy and the migrations; a one-line free-space refusal naming what to free. The guide
  states the duration. (Corrected: the copy's share written in place of an expected wait, lot 2's D3.) *Ten silent minutes with the webui unreachable are when an operator restarts, and a traceback
  in bytes helps nobody.* No waiting page in the webui: *it would serve once per upgrade.*
- **D7. `merge` runs on a stopped node only**: the docs say to stop the crawler first, and `merge` refuses a catalog a
  crawler holds. (Corrected: refined by lot 2's D4: a merge refuses a held destination, `--output` still reads a running
  node's catalog.) *Merging into a live node is not a use case the operator wants to support now; today the crawler
  loses its writes during the merge's lock.*
- **D8. After applying migrations, the crawler gives back to the system the memory the migrations used.** *It holds
  several hundred megabytes for nothing until its next restart, and the fix is simple.*
- **D9. Two rare raw metadata shapes lose a value at the migration, accepted**: a field repeated within one reading
  keeps its last value, and a plain `media` field beside `media.*` ones is dropped. *Only data written before v3 can
  hold the first and no release since v3.0 writes the second; the operator's catalog holds neither, and the one other
  known deployment is near identical.* The guide states the limit.

### Lot 3: configuration validation

- **D10. Validation lists every problem in one pass**, across the three files, removed, moved and renamed keys
  included, in `validate-config` and at start. *An operator who skipped part of the guide fixes everything in one
  round instead of one run per refusal.*
- **D11. No command rewrites a 4.x configuration.** *D10 already names each key with its exact action; a rewriter
  would add a dependency, to keep the files' comments, for one use per operator.*

### Lot 4: fault isolation

- **D12. An unexpected error in one independent part of the crawler does not stop the node, and a degraded mode stays
  viable.** *Today any unexpected error in any loop stops every loop, downloads and webui included: a bug on one
  search channel stopped a healthy one, and a failing node metric write would stop the crawler as well.* Which parts
  are independent, which conditions deserve a real stop and how a degraded part tells the operator are designed in
  this lot's own Discuss, from the audit's inventory (appendix A, lot 4).
- **D13. The retry delay recognises its cap without computing past it; the attempts counter stays true.** *The
  counter is a fact the Node page shows; the defect is the computation.*

### Lot 5: the webui

- **D14. The webui reads the database off its event loop.** *One slow page holds every other request, `/metrics` and
  `/health` included; v5 is the version that starts filling the source tables, whose pages were never measured at
  scale.*
- **D15. The Node page's downloads table gains an abandon button on a queued or downloading download and a retry
  button on a failed one**, written by the crawler itself like the dashboard's pause and restart. *Telling the
  operator to edit `local.db` by hand is absurd; an abandon has no other clean way, since the crawler sends back a
  download that disappears from aMule.*
- **D16. The heavy file page leaves v5**, for a `BACKLOG.md` feature entry written at lot 5's Wrap: group consecutive
  identical readings into one row with its span and count. *Its display deserves its own discussion.*

### Lot 6: the release chain

- **D17. v5 ships through one or more release candidates, `v5.0.0-rcN`.** *The operator's node is where the facts no
  isolated test can prove get checked: High-ID through the real VPN with the live port change, the crawler behind the
  tunnel, the memory after the real migration.*
- **D18. A release candidate tag publishes its own image tags only, never `latest`, carries its version label, and
  makes a GitHub prerelease.** *Today any `v*` tag becomes `latest` and an rc tag would be labelled a dev version.*
- **D23. An rc is installed by editing the two `image:` lines of `deploy/`'s compose files**, which the rc's release
  notes name; the final release's compose files bring back `latest`. *For one or two rcs installed by the operator,
  an edit costs nothing and adds no surface; a version variable would mostly serve pinning, which nobody asked for.*

### Lot 7: the migration guide and the docs

- **D19. The guide and the docs are rewritten last, against the behaviour lots 1 to 6 leave.** *They describe the
  final behaviour, and every defect the audit found in them is a fact of `main` today.* Their shape (a checklist
  before the first step, a validation step before the start, the changes sorted by who must act) is lot 7's proposal
  for its own Discuss.
- **D20. After a long stop, a download absent from aMule still fails at the first cycle; the guide says to check the
  log and to retry from the Node page or by re-adding the link in aMule.** *An absence from aMule is a strong signal
  (an entry stays queued even with no source, established with the operator in
  `2026-09-13-real-disk-cap-and-lost-download-ttl.md`), the end-to-end run kept every download in progress, and
  amuled loads every partfile before it spawns amuleapi.*

### After the v5.0.0 tag

- **D21. The daily Grype scan moves to the two p2pwatch images and drops the frozen 4.x one, after the final tag and
  not before**, which supersedes the backlog entry's "before the next release". *The scan reads `latest`, which only
  the final tag publishes; an alert no fix can follow is noise, and the 4.x image only serves the rollback.*
- **D22. The install page's "no p2pwatch release yet" banner goes in a docs push right after the release.** *The tag
  does not rebuild the site.*

## The lots

| Lot | Theme | Decisions | Order |
|---|---|---|---|
| 1 | aMule container | D1, D2, D24 (Corrected: D24 replaced by lot 1's D3) | first: the worst defect, and the riskiest claim |
| 2 | migration and first start | D4 to D9 | any time before 7 |
| 3 | configuration validation | D10, D11 | any time before 7 |
| 4 | fault isolation | D12, D13 | before 5: its design frames the webui's failure behaviour |
| 5 | webui | D14 to D16 | after 4 |
| 6 | release chain | D17, D18, D23 | before rc1 |
| 7 | migration guide and docs | D19, D20 | last: it describes what 1 to 6 leave |

Each lot's tier is decided when it opens. The path to v5.0.0:

1. Lots 1 to 7 merged.
2. Tag `v5.0.0-rc1`; a copy of the operator's node upgraded by the guide, then the node itself.
3. The acceptance rows checked where each table below says; a defect found becomes a fix and another rc.
4. Tag `v5.0.0`, then D21 and D22.

## Acceptance

Commands for each row: appendix C. The audit's instruments are committed under
`agents/reference/2026-11-04-v5-audit-instruments/`, to be rerun at rc.

### On the operator's node, at rc

| Check | Today (`fc8c9eae`) | At v5.0.0 |
|---|---|---|
| A forwarded port change under the VPN | amuleapi gone, `ed2k` `healthy` | amuled's listening port follows the forwarded one, amuled's pid unchanged, amuleapi answering |
| High-ID | not testable offline | ed2k reports High-ID after a forwarded port change |
| The crawler's resident memory (`VmRSS`) after the first start | 330 MB just after opening | under 150 MB |
| The crawler's traffic | not testable offline | outside the tunnel, as the guide says |

### On a copy of the operator's node

| Check | Today | At v5.0.0 |
|---|---|---|
| The guide applied literally | `p2pwatch` restart-loops on a missing environment variable | the node starts |
| Content after the migration | every observation, decision and download equal | unchanged |
| A stop during the longest migration, then a restart | a second full copy | no second copy, the migration replayed |
| A stop during the final `VACUUM`, then a restart | replayed (version 8) | replayed |
| A `data/` short of space | 52-line traceback | one line naming what to free |
| The first start's log | silent for 6 then 4 minutes | a line before the copy, progress during it and the migrations |
| The 4.x `crawler.yml` and `matcher.yml` left unmigrated | one refusal per run | every refusal in one run |
| `merge --into` a running node's catalog | the crawler loses writes | refused |
| amuleapi stopped inside `ed2k` | `healthy` | `unhealthy` |
| The port-sync killed inside `ed2k` | s6 restarts it alone | the container exits and Docker restarts it (Corrected: exit 0, lot 1's D3) |
| `docker compose stop ed2k` | amuled shuts down cleanly | amuled shuts down cleanly |

### In tests and CI

| Check | Today | At v5.0.0 |
|---|---|---|
| An unexpected error in one search channel | the crawler stops | the other channel's searches go on, and the degraded part shows as lot 4 designs |
| A page that sleeps 10 s | `/health` waits for it | `/health` answers in under 100 ms |
| The 1025th consecutive failure of a channel | `OverflowError`, the crawler stops | the delay at its cap |
| Abandon and retry from the Node page | absent | the row's state changes, the next cycle follows it |
| An rc tag | would become `latest`, labelled a dev version | its own tags only, labelled `5.0.0rcN`, a GitHub prerelease |

What must not change: every observation, decision and download of a 4.x catalog survives the upgrade field by field;
the matching decisions on the real catalog; the rollback to 4.1.0 as the guide writes it; `mulewatch:latest` stays
4.1.0.

## Adjacent backlog items

- **The Grype scan back on p2pwatch at the v5 release**: absorbed by D21, after the final tag; deleted once it ships.
- **Test quality**, **mutation testing in the gate**, **contract tests for the fakes**, **a generic way to write the
  stubs**, **adopt ty**, **a rule test naming no rule**: tooling and test debt, nothing the operator meets in the
  upgrade; they stay open after v5.
- **`merge` refuses a source whose schema is not the node's**: D7 adds a refusal of a held catalog, not a schema
  check; it stays open.
- **Multi network stage 5**, **sort by first seen**, **the visitor's time zone**: features, after v5 by the decision
  that v5 ships without a new network.
- **New entry at lot 5's Wrap**: D16's grouped file history.

## Appendix A: the audit's findings, by lot

Measured 2026-11-03 and 2026-11-04 on `fc8c9eae`. The teammates' full reports were in the lead's gitignored
`.reviews/`; the instruments are in `agents/reference/2026-11-04-v5-audit-instruments/`, and each lot's spec
re-measures what it acts on.

### Lot 1

- CRITICAL: after every port-sync restart of amuled, amuleapi never listens again (3 of 3 against a fake gluetun):
  amuled SIGTERMs amuleapi without waiting (`amule.cpp:383-401` at the pin `0db738ed`), the old one releases 4711
  about 205 ms after `s6-svc -wD` returns, the new one fails to bind and returns 0 (`App.cpp:625-627`), and amuled
  relaunches only a child that exited non-zero. `PATCH /api/v1/preferences` on `connection.tcp_port` and `udp_port`
  moved TCP, UDP and server UDP in 2 ms, saved `amule.conf`, both pids unchanged. The fallback, an s6 `finish` for
  amuled that waits for amuleapi (SIGKILL after 10 s, `timeout-finish` 12000), proven 3 of 3, the SIGKILL path on an
  amuleapi frozen by SIGSTOP.
- MAJOR: both images build on `debian:trixie-slim@sha256:a99cfc51…` (2026-09-18): 5 fixable High CVEs (libssl3t64,
  libpcre2-8-0), fixed in the current digest.
- MAJOR: Dependabot has never updated `packages/amule/Dockerfile` (its `uv` is 0.12.21, the crawler's 0.13.6); cause
  unproven.
- MINOR: `AMULE_API_PASSWORD` passes on amuleapi's argv; `--set-admin-pass-stdin` exists at the pin.
- MINOR, unproven: after a container restart the port-sync can call s6 before `s6-supervise` listens (moot with D24). (Corrected: D24 replaced by lot 1's D3; closes with lot 1's block 70.)
- Facts for D24 (Corrected: D24 replaced by lot 1's D3, s6 kept): s6's four roles today are running amuled and the port-sync side by side, restarting the one that
  dies, letting the port-sync stop and start amuled (gone with D1), and the healthcheck's `s6-svstat` (gone with D2).
  A manual `s6-svc -r` of amuled never lost the API in 12 runs (s6 respawns about 1 s after the signal, the old
  amuleapi exits in 145 to 475 ms): a margin, not a guarantee, which a container restart makes moot. Waiting on the
  first of two children needs bash's `wait -n` (Debian's bash is in the image); the entrypoint becomes the
  container's main process, so it forwards Docker's stop to both and compose sets `init: true` to reap them. The
  docs' three `s6-svc -r` commands become `docker compose restart ed2k` (lot 7).

### Lot 2

- MAJOR: a stop after catalog 0006 makes the restart write `pre-0007` (7.50 GB, 226 s; 22.8 GB in `data/`, 2.9 times
  the catalog); on a `data/` sized to twice the catalog the second start is refused
  (`472527440 bytes needed in /data, 324317184 free`).
- MAJOR: `merge --into` holds the catalog's write lock 21.7 s per real-sized source; the crawler's connections wait
  Python's default 5 s, then fail with `database is locked`.
- MINOR: the free-space refusal is a 52-line traceback ending in bytes; a SIGTERM during the copy exits 0 with no log
  line; a value a migration's SQL function refuses reads `user-defined function raised exception`, naming nothing.
- MINOR: "up to twice the database" is not a bound for a catalog that folds little (0007 builds the new tables beside
  the old, 0008 rewrites them in the WAL).
- MINOR: `local/0010`'s `UPDATE scheduler_state ... 'channel_backoff'` can never match (dead statement).
- MINOR: the crawler stays at 360 to 418 MB (`docker stats`) after the migration. Cause proven: 0007 and 0008 set
  `cache_size = -262144`, the cache grows to about 256 MB, and when the pragma returns to -2000 SQLite frees those
  pages into glibc, whose heap only shrinks from its top. Just after opening, at full scale: `VmRSS` 330 MB, SQLite
  using 3.0 MB, glibc holding 288 MB of which 8 MB in use. Reopening the connection, `PRAGMA shrink_memory` or
  `cache_size = 0` alone leave it at 131 MB on a 236 MB catalog; `malloc_trim(0)` alone brings it to 32 MB. Full
  scale: `malloc_trim(0)` 330 to 49 MB, reopening the catalog connection then a second trim 40 MB; the whole crawler
  with a trim after each open 104 to 108 MB `VmRSS` (149 MB in `docker stats`, which counts kernel memory nothing
  frees), 79 MB on a fresh boot. The trim goes in as an injected function, so a test checks it without patching.
- MINOR, latent: the raw metadata fold drops a plain `media` name beside `media.*` names and keeps the last value of a
  repeated name (D9); the EC mapper of v0.5 to v2 kept duplicates on purpose.
- MINOR: the copy is published by `os.link`; on a `data/` whose filesystem refuses hard links (vfat, exFAT, SMB
  without Unix extensions), every start would write the full copy, fail and delete it. `os.link` works on a Docker
  Desktop (Linux) bind mount and on a named volume; Desktop on macOS or Windows is unproven.

### Lot 3

- MINOR: `validate-config` returns the first problem of the first wrong file; up to 11 refusals in a 4.x
  `crawler.yml` and 2 in `matcher.yml`.

### Lot 4

- MAJOR: `backoff_delay` computes `base * factor ** (attempt - 1)` before capping; the 1025th consecutive failure
  raises `OverflowError` (3 days 12 h 48 min at base 2 s), which escapes `SearchWorker.run_task` and ends the
  crawler; the attempts are persisted, so every restart repeats it. Present since v4.
- Inventory (11 probes, `fault-isolation/test_fault_isolation.py`): every loop shares one `TaskGroup` with no
  restart, Docker being the only supervisor; an unexpected error in a search task (a kad bug stopped a healthy ed2k
  channel after 812 good searches), the status loop, the download cycle, the source watcher, the cataloguer (which
  catches only `StoreError`) or the dispatcher's node metric writer stops the crawler; one in the startup
  reevaluation is a crash loop. Already isolated: the notifier, the webui thread (`webui degraded`), each webui
  request (a 500, the app serving on), every step for `StoreError`. "Never raises" is a convention only; `/health`
  always answers ok, compose gives `p2pwatch` no healthcheck, and a crash loop shows in the operations channel only
  as repeated "node online". Candidate real stops: an invalid config, a failed migration, a corrupt or persistently
  unwritable database, a refused password.
- MINOR: a SIGTERM during the startup reevaluation is handled only when the pass ends.
- MINOR: `shutdown_deadline_seconds: 10.0` equals Docker's default stop grace; the service sets no
  `stop_grace_period`.
- MINOR: `_crawl` reports any `TimeoutError` as the shutdown deadline, exit 0.

### Lot 5

- MINOR, unproven: every page handler reads SQLite on the webui's one event loop (D14); off it, a reader connection
  per worker thread, since `open_reader` serves the thread that opens it.
- MINOR: the "read-only" console creates empty files through `ATTACH DATABASE` and `VACUUM INTO`.
- MINOR: a `?page=` above about 1.8e17 answers 500 (SQLite integer overflow).
- MINOR: a non-UTF-8 console POST answers 500.
- MINOR: the busiest file's page renders 22 951 rows, 6.13 MB, over the default 7 days (D16).
- Fact: on the migrated real catalog, every page query under 0.3 s, no full scan of `observations`.

### Lot 6

- MAJOR: `.dockerignore`'s `.env` and `*.db*` patterns match only at the context root, so a nested `.env` or catalog
  enters the build context and BuildKit's cache; the published images are unaffected.
- MINOR: each `publish` leg pushes `5.0.0` and `latest` before it signs; one leg failing leaves the two images'
  `latest` inconsistent.
- MINOR: `latest` is enabled for any `refs/tags/v*`; hatch-vcs's tag pattern `^v(\d+\.\d+\.\d+)$` labels an rc tag a
  dev version (D18).

### Lot 7

- CRITICAL: step 4 replaces `base.compose.yml`, where 4.x operators mapped every `${VAR}` of `crawler.yml`, and says
  to carry over ports only; the operator's node restart-loops on `DISCORD_COMMUNITY_URL`.
- MAJOR: the backup box precedes "stop the node"; "the `emule_*` metrics become `p2pwatch_*`" is wrong for 7 of 18;
  the removed compaction tool is unannounced (a catalog compacted by 4.x's tool stops migration 0006); the two new
  community alerts (`first useful`, `reappeared`) are unannounced; `/controls` and the `/files/<md4>` URLs are gone
  unannounced; the install page's banner (D22).
- MINOR (17): `rm ... gluetun.compose.yml` fails on a node without that file; "`-f gluetun.compose.yml`" is
  ambiguous for a renamed VPN stack; where the 5.0 `deploy` folder comes from is unsaid; the new duration bounds; the
  operations notifications that change; the 4.x tool commands (`--user amule`, s6) that break; a set `node_id`
  changes the node's id; the `VPN_PORT_FORWARDING` wording; the moot 9090 clause; `?done=restart` was `/controls`';
  Compose 2.20 is required by `include:` (unproven); "Up in ~30 s" against 10 min 44 s; `limits.md`'s durations from
  October; the 4.x docs URL answers 404; the signer identity of `mulewatch:latest` is not given;
  `troubleshooting.md:70` says an amuled restart restarts amuleapi; the two manual `local.db` procedures (D15).
- Facts for D20: amuled loads every partfile synchronously (`LoadMetFiles`, `amule.cpp:1203`) before spawning
  amuleapi (`StartAmuleApi`, `:1452`); `/downloads` answers 503 until amuleapi's first EC snapshot, on which our
  client skips the download cycle. The operator's `local.db` holds 25 downloads, 20 in progress and 5 completed.

## Appendix B: what the audit proved sound

| Check | Method | Result |
|---|---|---|
| Full-scale migration | the guide applied to a reflink copy of the operator's node, direct variant, internal network; `migration-e2e/compare.py` against the original read-only | 15 763 676 observations in bijection per file over every column; 16 477 decisions and 25 downloads equal; a negative control with three planted changes reports exactly three |
| Real data | read-only scan of `catalog.db` and `local.db` (both at version 5) for every value a migration would reject or alter | 0 |
| Interrupted migration | SIGKILL during the copy, 0007, 0008, 0009 on a 346 MB synthetic catalog, then restart; at full scale SIGKILL during 0007 and SIGTERM during the copy | every end state identical to an uninterrupted run |
| Matching | v4.1.0's and `main`'s engines over the 2 162 files, 180 targets | 0 decisions and 0 of 389 160 explanations differ; the first v5 start wrote 0 rows; two altered rules show 4 and 19 differences |
| Webui at scale | 29 page queries with `EXPLAIN QUERY PLAN` on the migrated catalog; HTTP on the busiest file | all under 0.3 s; 0.385 s mean over HTTP |
| Rollback | both procedures of the guide | original content back, 4.1.0 boots on it |
| Config refusals | each 4.x key put back alone | every message identical to the guide's |
| Integration suites | `api`, `download`, `orchestration`, `compose_integration` against an isolated amuled | green (the known Docker Desktop completion test aside) |
| Release walk-through | `release.yml` on a `v5.0.0` tag, Grype as the release runs it | both images under the names `deploy/` pulls, signed; `mulewatch:latest` stays 4.1.0; aMule 3.2.0 pinned; tag-only Grype steps pass |
| First start figures | the operator's catalog, Docker Desktop on btrfs | 10 min 44 s (copy 380 s, 0007 225 s), peak 15.6 GB in `data/`, 396 MB peak memory |

## Appendix C: acceptance, in detail

Paths relative to `agents/reference/2026-11-04-v5-audit-instruments/`. Each lot's spec turns its rows into tests where
a test can hold them.

| Row | Command, and the output that fails it |
|---|---|
| Port change under the VPN | on the node, gluetun forwarding a new port: `docker compose logs ed2k` shows the port-sync applying it; `grep -E '^(Port|UDPPort)=' ed2k/amule/amule.conf` and amuleapi's `GET /api/v1/preferences` show it; `pidof amuled` unchanged; fails on a restart line or a 4711 refusal |
| High-ID | the webui's `p2pwatch_channel_connectable{channel="ed2k"}` at 1 after the change; fails at 0 for over 5 minutes |
| Memory | `docker compose exec p2pwatch grep VmRSS /proc/1/status` once the first start's reevaluation ends; fails at 150 MB or more |
| Traffic outside the tunnel | the public address seen from `p2pwatch` against the one seen from `ed2k-gluetun`; fails if they are equal |
| Guide applied literally | the guide on a fresh reflink of the node, then `docker compose ps`; fails on `Restarting` |
| Content after migration | `migration-e2e/compare.py` on the migrated copy against the original; fails on any `DIFF` |
| Stop during the longest migration | `docker kill` during 0007, restart, `ls data/`; fails on a second `pre-*` copy |
| Stop during `VACUUM` | `docker kill` during the reclaim, restart, file size; fails if the catalog stays oversized |
| Short of space | `migration-e2e/freespace.sh`; fails on a traceback or on a line in bytes |
| First start's log | `docker compose logs -t p2pwatch`; fails on a gap over 60 s before `crawler started` |
| Unmigrated config | `validate-config` on the 4.x files; fails if any of the 13 refusals is missing from one run |
| `merge` on a running node | `docker compose exec p2pwatch python -m p2pwatch merge --into /data/catalog.db ...`; fails if it runs |
| amuleapi stopped | kill amuleapi inside `ed2k`, `docker inspect` health after the interval; fails on `healthy` |
| Port-sync killed | kill the port-sync inside `ed2k`; `docker inspect -f '{{.RestartCount}}'` rises and `ed2k` is healthy again; fails if the container stays up without a port-sync (Corrected: held by lot 1's CI rows) |
| `ed2k` stopped | `docker compose stop ed2k`, then its log; fails without `aMule shutdown completed` |
| Error in one channel | a test injecting a failing kad client; fails if the ed2k searches stop |
| Slow page | a test sleeping 10 s in one page while timing `/health`; fails at 100 ms or more |
| 1025th failure | `fault-isolation/test_backoff_overflow.py`, turned into a unit test; fails on `OverflowError` |
| Abandon and retry | a webui test posting each action; fails if the row's state does not change |
| rc tag | the release workflow on `v5.0.0-rc1`: `ghcr.io` tags list and `gh release view v5.0.0-rc1 --json isPrerelease`; fails on a `latest` move, a `dev` label or `false` |
