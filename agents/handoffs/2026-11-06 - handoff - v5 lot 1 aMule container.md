# Handoff: v5 lot 1, the aMule container (tier Spec)

Drafted by block 80's teammate, corrected by the closing block's (90). Spec:
`agents/specs/2026-11-04-v5-amule-container.md`, lot 1 of `agents/specs/2026-11-04-v5-release-readiness.md`.

## Current state

- **The port-sync never restarts amuled** (D1): each round reads amuled's TCP port with `GET /api/v1/preferences`
  (`connection.tcp_port`) and, when gluetun forwards another one, sets both ports live with `PATCH` on the same route.
  It keeps amuleapi's token and logs in again once on a `401`. amuleapi not ready (refused, timed out, `503` before its
  first snapshot, a `401` after the one re-login) is logged at `info` and retried at the next poll; a rejection (`400`,
  above 65532, a port held, the EC port) is logged at `error`, amuled stays on its port, the next poll retries;
  anything else propagates and the port-sync exits. The port-sync reads no file of amuled's and calls no s6 command.
- **A service that exits unasked takes the container down** (D3): `docker/services.d/{amuled,port-sync}/finish` run
  `s6-svscanctl -t` when `s6-svstat -o wantedup .` reads `true`; `restart: unless-stopped` on `ed2k` and
  `ed2k-gluetun`, asserted by the deploy render test, restarts it. `docker stop` and `s6-svc -d` leave it up.
- **The healthcheck asks amuleapi** (D4): `python -m p2pwatch_amule health`, exit 0 when `GET /api/v1/health` answers
  `200` with `ec_connected` true (`ApiHealthClient.is_api_healthy`), as `CMD` in both the deploy and the smoke stacks.
- **amuled runs on wxWidgets 3.2.12** (D6), built in the image without the GUI, pinned by checksum, declared in
  `amule.cdx.json` with its CPE; a CI step checks `ldd` and `amuled --version`, and both SBOM checks (`validate.yml`,
  `release.yml`'s aMule leg) assert `pkg:generic/wxwidgets@` beside aMule's. `BACKLOG.md` "Postponed" says when to
  drop the build.
- **The image's upkeep** (D7 to D10): the API password reaches amuleapi on stdin (`--set-admin-pass-stdin`);
  Dependabot has one `docker` entry per image, `cooldown: default-days: 0`; both images on
  `debian:trixie-slim@sha256:a72b4433...` (`libssl3t64` and `libpcre2-8-0` at `~deb13u3`) and on `uv` 0.13.7, the
  same digest, which Dependabot's #637 brought to `main` on 2026-11-06 under the whole stack (not block 10); under the
  VPN, gluetun's control server answers only `GET /v1/portforward`, its role inline in `deploy/ed2k/vpn.compose.yml`
  (`configs:` with `content:`, Compose 2.23.1 or later).
- **The unit gate binds no fixed host port**: `build_command_line` takes amuleapi's URL, `__main__` passes
  `AMULE_API_URL`, one test asserts it is `http://127.0.0.1:4711`. The amule suite passes beside a listener on
  `0.0.0.0:4711`, as a node on the same host publishes it.
- **Gone**: `PORT_SYNC_RESTART_MIN_SECONDS` (never released), `ServiceSupervisor.stop_amuled` and `start_amuled`, the
  port-sync's `amule.conf` reader and writer wiring, `tcp_listen_port`, `s6-svperms` in the port-sync's run script,
  `MonotonicClock.now()` and `MonotonicInstant` of `p2pwatch_amule` (the crawler keeps its own).

## What was built, block by block

| # | PR | Block | Lines, files |
|---|---|---|---|
| 10 | #631 | password on stdin, Dependabot, bases, gluetun's routes | 86, 12 |
| 20 | #634 | wxWidgets 3.2.12 | 71, 6 |
| 30 | #636 | the `health` command on amuleapi | 401, 16 |
| 40 | #639 | the healthcheck on it; a dead service restarts the container | 173, 8 |
| 50 | #640 | the port set live, the restart kept as fallback | 477, 16 |
| 60 | #641 | the token kept, amuleapi not ready retried | 274, 8 |
| 70 | #642 | the restart removed | 520, 19 (accepted by the operator) |
| 75 | #643 | `MonotonicClock.now()` and `MonotonicInstant` removed | 127, 9 |
| 80 | #644 | the port read through amuleapi | 316, 15 |
| 90 | this one | closing: the holistic findings, the records | see its pull request |

- **Block 75** is the operator's class 2 of 2026-11-06 (found by block 70): no `src` of `p2pwatch_amule` read `now`
  once the restart floor left, and vulture misses it since the crawler has a `.now`. It was written in block 80, which
  then passed the file bound (23 files), and split out along its commit. The clock contract now states `sleep`'s
  promise through an `elapsed_during` fixture each implementation supplies (the system clock's test reads
  `time.monotonic_ns()`, the fake's sums its recorded sleeps).
- Departures, from the block reports (each marked `(Corrected: ...)` in the spec by block 90):
  - Block 10 bumped the Debian digest by hand: Debian re-pushed `trixie-slim` during the lot and the 3-day cooldown
    held Dependabot's digest back twice. It left the `uv` stages to Dependabot's #637 (merged 2026-11-06). Its
    class 1, merged apart as #632: `agents/reference/` out of `ruff` and `ast-grep scan`.
  - Block 20: `libwx_baseu` holds no version string (the only copy of `wxVERSION_STRING` is UTF-32, in `_net`), so the
    CI step reads `amuled --version` (`wxBase v<WX_VERSION>`) and checks both wx libraries resolve from
    `/usr/local/lib`. wx builds on Debian's regex and zlib, without XML; the runtime also drops `libglib2.0-0t64` and
    gains `libpcre2-32-0` and wx's licence.
  - Block 30: no composition class for `health` (it parses no setting); its driving port's fake sits in
    `tests/fakes/application/use_cases/`.
  - Block 40: the render test also asserts `ed2k`'s healthcheck command; pids read from `/proc` by argv prefix.
  - Block 50: the `PATCH` tried on every round, inside the restart window too; the smoke also asserts `amule.conf`
    holds the new port, amuled saving it itself.
  - Block 60: a timeout is amuleapi not ready (the lead's request, a fix-back after the PR opened); a refused login,
    a `429`, a garbled reply or a login without a token propagate; any `400` to the `PATCH` is a rejection.
  - Block 70: the port-sync's run script also lost its wait for `supervise/control`, closing the umbrella's finding
    on the port-sync calling s6 before `s6-supervise` listens; `FakeAmuleConfStore.write_error` deleted.
  - Block 80: the read's `400` is not a rejection (only the `PATCH`'s is) and propagates; preferences without an
    integer `connection.tcp_port` (a JSON `true` included) propagate as `ListenPortError`.
  - Sizes: block 60 274 lines for about 120, block 40 173 for about 250, both outside the estimates' 25 %.

## The holistic review's findings and their exits

Review: `.reviews/v5-lot1-holistic.md` (0 CRITICAL, 2 MAJOR, 14 MINOR). Every one is fixed in block 90 unless its
line says otherwise.

| Severity | Finding | Exit |
|---|---|---|
| MAJOR | the unit gate binds host port 4711, which a node on the same host publishes | fixed: the URL a parameter of `build_command_line`, the test on an ephemeral port, the 4711 fact one assertion on `AMULE_API_URL`; the old test fails `OSError: [Errno 98] Address already in use` beside a `0.0.0.0:4711` listener, the new suite passes (230) |
| MAJOR | the aMule image's `uv` not on the crawler's (D9) | fixed outside the lot: Dependabot's #637, merged to `main` on 2026-11-06, under the whole stack; both Dockerfiles on `uv:0.13.7@sha256:96f40d39...`; the spec's D9 and block 10 marked |
| MINOR | refusal bodies cut to 100 bytes twice | fixed: the messages' slices dropped, `_head`'s bound kept; `_head` reading the whole body now fails both `500` cases |
| MINOR | `rstrip("/")` on a URL no operator writes | fixed: both calls and the tests' trailing `/` deleted |
| MINOR | `run_port_sync_loop`'s docstrings (restart, `OSError`) | fixed: sets amuled's ports live; raises `SettingsError` or `ListenPortError` |
| MINOR | contributor docs stale (architecture section 3, 4, 9; testing's smoke count; `.claude/CLAUDE.md:7`) | fixed |
| MINOR | `.claude/rules/amuleapi.md` lines 15 and 20 | fixed: a token survives an amuleapi restart, a password change refuses it; the ports set live, amuled saving `amule.conf` itself and never rewriting it on exit |
| MINOR | `vulture_whitelist.py`'s dead `capture_output` | fixed: deleted |
| MINOR | `MonotonicClock`'s docstring and the glossary row | fixed: the poll's sleep; the glossary row gains "`p2pwatch_amule`'s only sleeps" |
| MINOR | "ready" names two concepts | fixed: the health side renamed `is_api_healthy` (fake `is_healthy`, tests "healthy"/"unhealthy"), matching `ApiHealthClient`, `CheckApiHealth` and Docker's `healthy`, and leaving "not ready" to the port-sync's `ApiNotReadyError` |
| MINOR | the fake's `error` beside `read_error`; a test named after a restart | fixed: `set_error`; `test_another_failure_of_amuleapi_ends_the_loop` |
| MINOR | a repeated `ListenPortError` restarts the container in a loop | accepted limit, written in the spec's section 6; owner lot 4 (below) |
| MINOR | the SBOM checks assert aMule only, not wx | fixed: `pkg:generic/wxwidgets@<WX_VERSION>` in `validate.yml`, `pkg:generic/wxwidgets@` in `release.yml`'s aMule leg, SECURITY.md says both are enforced; both snippets run red (wx absent, or 3.2.11) then green on fixture files |
| MINOR | handoff draft corrections | fixed in this file |
| MINOR | two umbrella mentions of D24 unmarked | fixed: both marked `(Corrected: ...)` |
| MINOR | operator pages lot 7 rewrites | listed for lot 7 below, not edited |

## Accepted limits

- **A `ListenPortError` that repeats restarts the container in a loop**: a route renamed or a body changed by an aMule
  bump (`404`, a `400` to the login, malformed preferences) makes the port-sync exit, the container restart, and the
  next round, one poll after amuleapi listens again, exit again. Under the VPN amuled then restarts about once a minute
  for good, dropping transfers and Kad, while `ed2k` reads `healthy` most of the time. Signal: `docker inspect -f
  '{{.RestartCount}}' ed2k` rising, and the port-sync's traceback in `docker compose logs ed2k`. Mitigated by every
  amule-bump pull request running the smoke's port-sync test against the real amuleapi. Owner: lot 4 (the port-sync
  robust to its own errors).
- The others are the spec's section 6.

## For lot 7 (the operator pages, umbrella D19)

These pages describe behaviour this lot removed; lot 7 rewrites them, block 90 left them:

- `docs/troubleshooting.md`, about lines 250 to 265: the port-sync entries name the restart and log lines that no
  longer exist (`amule.conf's port is unreadable`, `amule.conf does not exist`,
  `amuled listens on <M>: restarting amuled`).
- `docs/limits.md:92`: "au-delà de 60 secondes, le port-sync renonce, relance amuled et réessaie après 5 minutes".
- `docs/troubleshooting-start.md:75`: "s6 relance amuled sur place et le conteneur reste `Up`".
- `docs/operate.md:101-114`: `s6-svc -r` "pour ne toucher qu'amuled", which since block 40 restarts the whole
  container; "sinon il relance amuled à son prochain changement de port".
- `docs/high-id.md`, Route A's two paragraphs and the last one: the port-sync "arrête amuled, écrit le nouveau port
  [...] puis le redémarre, au plus une fois toutes les 5 minutes", and "Pendant un redémarrage". Block 90 removed only
  the `PORT_SYNC_RESTART_MIN_SECONDS` row.
- The operator docs' s6 commands give way to `docker compose restart ed2k`.

## The lot's counts

From `gh run list --branch <branch>` and the pull requests' timelines (`head_ref_force_pushed`), on 2026-11-06 before
block 90's push:

- **Fix-backs: 2.** Block 10's Debian digest (17:09Z, a commit added to #631) and block 60's timeout (17:41Z, a commit
  added to #641).
- **Cascaded rebases: 1.** Block 10's fix-back moved #634, #636 and #639 (17:09Z); block 60's had nothing above it
  yet. Block 75's insertion rewrote no pushed branch (#643 and #644 opened after it).
- **Runs those re-triggered: 8**, 3 of them cancelled by a newer push: 1 on #631, 2 each on #634, #636 and #639, 1 on
  #641. Fewer than the lot's 10 blocks.
- **Rebases onto `main`: 2**, outside the fix-backs: #631 alone after #632 merged (16:04Z, 1 run), the whole stack
  after #637 merged (20:21Z, 16 runs started over the 9 branches, 7 cancelled by a second run on the same commit).
- **Bodies the operator called unreadable unprompted: none.**

## Pitfalls learned

- **Serena's `find_referencing_symbols` is unusable**: it returned nothing on `ApiNotReadyError` (block 70), raised
  `IndexError: list index out of range` (block 80), and returned `{}` on `ApiHealthClient/is_api_ready` (block 90),
  which `git grep -w` finds in 5 files. Every rename and deletion of blocks 70 to 90 was checked by `git grep -w` per
  name. Ask the operator for `/mcp reconnect serena`.
- **A unit test binds no fixed host port**: a node on the developer's host publishes 4711 on every interface, and a
  `127.0.0.1` bind beside a `0.0.0.0` listener fails `Address already in use`.
- **The image has no `kill` binary**: `sh -c 'kill -KILL <pid>'` (the shell's builtin), or Python's `os.kill`.
- **`docker compose logs` carries the `finish` lines** (s6-supervise's stdout); amuled's `logfile` is read from the
  host bind mount once the container has stopped.
- **`COPY --from` with a wildcard follows symlinks**: copy only `*.so.*.*.*` and let `ldconfig` make the sonames.
  `make install-strip` names GUI libraries a `--disable-gui` build never makes: strip with `--strip-unneeded`.
- **urllib wraps a refused connection or a connect timeout in a `URLError`** whose `reason` is the error; a read
  timeout and a garbled status line arrive unwrapped. `HTTPStatus(code)` raises outside the enum: test a range.
  An `HTTPError` holds its connection open until closed; `read(100)` on a body cut short returns what arrived.
- **pytest skips an abstract test class silently**: a contract whose new abstract fixture an implementation lacks
  runs none of its tests rather than failing.
- **vulture reads a callback `Protocol`'s keyword as unused** (`input`, beside `user` and `extra_groups`), and misses
  a method unused in one package when another package's `src` has a member of the same name.
- **Debian re-pushes `trixie-slim` often**: the default Dependabot cooldown counts from the latest push.
- **The compose smoke's completion test fails on Docker Desktop** at its `-shm` step, as documented; every other
  smoke test passed on each block that ran it.

## Not validated

- **High-ID after a live change behind a real forwarding VPN**: rc1 on the operator's node, with D2's described
  fallback should it be lost.
- The rc1 rows of the spec's section 4, each on the operator's node:

| Row | Passes when |
|---|---|
| A forwarded port change under the VPN | the listening port follows, amuled's pid unchanged, amuleapi answering |
| High-ID | ed2k connectable after a port change |
| `docker compose stop ed2k` | `aMule shutdown completed.` in amuled's log |
| gluetun's control server, from the compose network | `GET /v1/portforward` answers, `PUT /v1/vpn/status` gets `401` |
| A dead service | `RestartCount` rises, `ed2k` healthy again |
| amuled's start, `Initialising` to amuleapi listening | under 2 min (`start_period` plus `interval x retries`) |

- Docker's restart on the container's exit is not in the smoke (no policy there on purpose): proven in the lot's s6
  probe only (restart 0.13 s after exit 0).
- The wx use-after-free itself: no `server.met` or `nodes.dat` download ran locally; the arm64 image builds only in CI.
- The SBOM's wx assertion on a real SBOM: `validate.yml`'s at this pull request's run, `release.yml`'s at the next
  tag; locally only on fixture files.
- GitHub's acceptance of `cooldown: default-days: 0`, and a Dependabot job "docker in /packages/amule": the next weekly
  run after merge.
- A kept token's `401` at its 24 h expiry: from aMule's source, never run. (The port-sync restarts with the container
  and holds no token across the boot's password reset.)
- The first round before amuleapi listens is not reachable in the smoke; covered by a composition test against a
  closed port.

## Next step

The operator reads the whole stack (#631 to #644 and block 90) and merges it with `gh stack merge --rebase`; then rc1
on the operator's node, the rows above, High-ID first. Lot 4 then takes the port-sync's robustness, the restart loop
included; lot 7 the operator pages listed above.
