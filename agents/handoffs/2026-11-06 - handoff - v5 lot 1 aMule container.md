# Handoff: v5 lot 1, the aMule container (tier Spec)

Draft by block 80's teammate, for the closing block (90) to correct. Spec:
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
  `200` with `ec_connected` true, as `CMD` in both the deploy and the smoke stacks.
- **amuled runs on wxWidgets 3.2.12** (D6), built in the image without the GUI, pinned by checksum, declared in
  `amule.cdx.json` with its CPE; a CI step checks `ldd` and `amuled --version`. `BACKLOG.md` "Postponed" says when to
  drop the build.
- **The image's upkeep** (D7 to D10): the API password reaches amuleapi on stdin (`--set-admin-pass-stdin`);
  Dependabot has one `docker` entry per image, `cooldown: default-days: 0`; both images on
  `debian:trixie-slim@sha256:a72b4433...` (`libssl3t64` and `libpcre2-8-0` at `~deb13u3`), the aMule image on the
  crawler's `uv`; under the VPN, gluetun's control server answers only `GET /v1/portforward`, its role inline in
  `deploy/ed2k/vpn.compose.yml` (`configs:` with `content:`, Compose 2.23.1 or later).
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
| 75 | to come | `MonotonicClock.now()` and `MonotonicInstant` removed | 127, 9 |
| 80 | to come | the port read through amuleapi | 316, 15 |
| 90 | to come | closing | |

- **Block 75** is the operator's class 2 of 2026-11-06 (found by block 70): no `src` of `p2pwatch_amule` read `now`
  once the restart floor left, and vulture misses it since the crawler has a `.now`. It was written in block 80, which
  then passed the file bound (23 files), and split out along its commit. The clock contract now states `sleep`'s
  promise through an `elapsed_during` fixture each implementation supplies (the system clock's test reads
  `time.monotonic_ns()`, the fake's sums its recorded sleeps).
- Departures, from the block reports:
  - Block 10 bumped the Debian digest by hand: Debian re-pushed `trixie-slim` during the lot and the 3-day cooldown
    held Dependabot's digest back twice. Its class 1, merged apart as #632: `agents/reference/` out of `ruff` and
    `ast-grep scan`.
  - Block 20: `libwx_baseu` holds no version string (the only copy of `wxVERSION_STRING` is UTF-32, in `_net`), so the
    CI step reads `amuled --version` (`wxBase v<WX_VERSION>`) and checks both wx libraries resolve from
    `/usr/local/lib`. The spec's "the library embeds `wxWidgets 3.2.12`" is to be marked `(Corrected: ...)`.
  - Block 30: no composition class for `health` (it parses no setting); its driving port's fake sits in
    `tests/fakes/application/use_cases/`.
  - Block 40: the render test also asserts `ed2k`'s healthcheck command; pids read from `/proc` by argv prefix.
  - Block 50: the smoke also asserts `amule.conf` holds the new port, amuled saving it itself.
  - Block 60: a timeout is amuleapi not ready (the lead's request, a fix-back after the PR opened); a refused login,
    a `429`, a garbled reply or a login without a token propagate.
  - Block 70: the port-sync's run script also lost its wait for `supervise/control`, closing the umbrella's finding
    on the port-sync calling s6 before `s6-supervise` listens; `FakeAmuleConfStore.write_error` deleted.
  - Block 80: the read's `400` is not a rejection (only the `PATCH`'s is) and propagates; preferences without an
    integer `connection.tcp_port` (a JSON `true` included) propagate as `ListenPortError`.

## Left to the closing block

- The spec's block table and appendix A gain block 75; appendix A and B's wx check corrected (block 20).
- `port_sync_loop_runner.py`'s docstring ("restarts amuled"), `docs/contributing/architecture.md` section 9,
  `docs/contributing/testing.md:352`, `docs/migration-4x.md:259`, `docs/high-id.md`'s variable row,
  `.claude/rules/amuleapi.md`'s stale facts (amuled does not flush `amule.conf` on exit; a token survives an amuleapi
  restart, the boot's password reset invalidating it).
- `docs/troubleshooting.md`'s port-sync entries (about lines 250 to 265) still describe the restart and log lines
  that no longer exist (`amule.conf's port is unreadable`, `amule.conf does not exist`,
  `amuled listens on <M>: restarting amuled`); the operator docs' s6 commands are lot 7's (umbrella D19), these lines
  are this lot's to place.
- The holistic review, `BACKLOG.md`, the counts of fix-backs, cascaded rebases and re-triggered runs (known so far:
  block 10's digest, block 60's timeout, block 75's insertion).

## Pitfalls learned

- **Serena's `find_referencing_symbols` is unusable**: it returned nothing on `ApiNotReadyError` (block 60's name, in
  block 70), then raised `IndexError: list index out of range` (block 80). Every deletion of blocks 70 to 80 was
  checked by `git grep -w` per name. Ask the operator for `/mcp reconnect serena`.
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
- The rc rows of section 4: a forwarded port change under the VPN, `docker compose stop ed2k`, gluetun's routes from
  the compose network, `RestartCount` rising on a dead service, amuled's start time against the healthcheck's 2 min.
- Docker's restart on the container's exit is not in the smoke (no policy there on purpose): proven in the lot's s6
  probe only (restart 0.13 s after exit 0).
- The wx use-after-free itself: no `server.met` or `nodes.dat` download ran locally; the arm64 image builds only in CI.
- GitHub's acceptance of `cooldown: default-days: 0`, and a Dependabot job "docker in /packages/amule": the next weekly
  run after merge.
- The `401` on a kept token after a container restart (the boot's password reset): from aMule's source, never run.
- The first round before amuleapi listens is not reachable in the smoke; covered by a composition test against a
  closed port.

## Next step

The closing block 90: the holistic review over `git diff origin/main...origin/<top branch>`, its findings fixed, the
items above, `BACKLOG.md` reconciled and this handoff corrected; then the operator's review of the stack and rc1.
