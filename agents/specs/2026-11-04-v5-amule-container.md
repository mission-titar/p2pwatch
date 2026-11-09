# v5 lot 1: the aMule container

Tier Spec. Discussed with the operator on 2026-11-04 and 2026-11-05, as lot 1 of `agents/specs/2026-11-04-v5-release-readiness.md`
(the umbrella), whose decisions D1 and D2 this lot implements and whose D24 it replaces (D3 below). Its findings are
the umbrella's appendix A "Lot 1". The decisions below are the operator's; their reasons are those given in the
discussion, the lead's included where the operator accepted a recommendation. Every measurement was re-run on
2026-11-04 and 2026-11-05 (appendix C). The spec's commit marks the umbrella's D24, its appendix A "Lot 1" facts for
D24 and its rc row "the port-sync killed" with `(Corrected: replaced by lot 1's D3)`.

## 1. In short

Today, under the VPN, the port-sync restarts amuled on every new forwarded port, and after each restart amuleapi
never listens again: the crawler is cut off from aMule for good while `ed2k` reports `healthy`. The lot removes the
restart: the port-sync changes amuled's ports live through amuleapi. s6 stays the container's supervisor, with one
change: when amuled or the port-sync exits without being asked to, the whole container goes down and Docker restarts
it. The healthcheck then tests what the crawler needs, amuleapi answering and linked to amuled.

On the way, the lot closes the image's other findings: amuled is built on a wxWidgets that fixes a use-after-free at
its start, the API password leaves amuleapi's command line, Dependabot updates the aMule image again, and both images
move to the current Debian base, which fixes five fixable High CVEs across both, and under the VPN gluetun's control server opens only
the forwarded port's read.

## 2. What the operator will see

- Under the VPN, a new forwarded port is applied within a poll (60 s by default) with no amuled restart: transfers
  and the Kad session carry on; amuled reconnects to an eD2k server, which must see the new port.
- `docker compose ps` shows `ed2k` `healthy` only when the crawler can drive aMule.
- If amuled or the port-sync stops on its own, the `ed2k` container restarts; it shows in its
  restart count and in a `finish` log line per service, the one that exited reading `wantedup true`.
- Restarting aMule is restarting its container, `docker compose restart ed2k`: lot 7's docs drop the s6 commands
  (umbrella D19).
- The VPN variant needs Docker Compose 2.23.1 or later (D10); lot 7's docs state it.
- `PORT_SYNC_RESTART_MIN_SECONDS` is gone. It was never in a release: the operator meets no change.

## 3. Decisions

- **D1. The port-sync changes amuled's TCP and UDP ports live through amuleapi, and never restarts amuled.** *A
  restart lets the new amuleapi start while the old one still holds its port, so it exits without an error and
  amuled never relaunches it (umbrella D1); the live change removes the trigger and keeps the transfers and Kad.*
  Whether it keeps High-ID behind a real forwarding VPN is checked on the operator's node at rc1. Blocks 50 to 80.
- **D2. The fallback is described, not written: should the live change lose High-ID at rc1, the port-sync writes the
  new port to `amule.conf` and exits, and the container restarts on it (D3).** *The operator counts on the live
  change; code that would never run if it works would only wait to be removed.* No block.
- **D3. s6 stays the supervisor; amuled or the port-sync exiting without being asked to brings the container down
  and Docker's restart policy restarts it.** *The operator wants no supervisor of our own: s6 is already in the
  image, and once the port-sync no longer restarts amuled, its one remaining gap is that it restarts a dead service
  alone instead of the container. A container restart restarts every process together.* This replaces the
  umbrella's D24 (s6 out, an entrypoint of our own) and keeps its accepted cost: a port-sync bug restarts amuled
  too, which reconnects to eD2k and Kad, and lot 4 makes the port-sync robust to its own errors. The operator
  weighed and set aside an off-the-shelf aMule image with glueforward for v5. Block 40.
- **D4. The healthcheck requires amuleapi to answer and to report its link to amuled.** *Today it checks amuled alone,
  so a container whose crawler has lost aMule reports `healthy` (umbrella D2).* Blocks 30 and 40.
- **D5. Nothing restarts the container when amuleapi alone is lost, an accepted limit.** *With the live change its
  one known trigger is gone; what remains (amuleapi stopped by hand, a failed start) is a case never observed, and
  it shows as `unhealthy` and as the crawler's operations alert after 2 minutes. Every way to act on it (a watch
  service, amuleapi as its own s6 service, a healthcheck that kills the container) costs more than the case.* No
  block.
- **D6. amuled is built on wxWidgets 3.2.12, built in the image until Debian ships the fix.** *Debian's 3.2.8 lacks
  the fix of a use-after-free during amuled's start-up downloads, which aMule's own builds (`amule-org/amule#1238`)
  and the main third-party image already avoid by building wx; no stable base image ships it today.* Pinned once by
  checksum; a `BACKLOG.md` "Postponed" entry says when to drop the build. A later wx security release reaches the
  image only by hand: the SBOM declares wx with its CPE, so Grype's scan names it once it covers this image again
  (umbrella D21). Block 20, apart from block 10 since it changes how aMule is built.
- **D7. The boot hands the API password to amuleapi on its standard input, not its command line.** *On the command
  line, any user of the host reads it in `ps` during the boot.* Block 10.
- **D8. Dependabot watches each image's directory in an entry of its own.** *With one entry over both, an open pull
  request for the crawler's image made every run skip the aMule image: it has never been updated.* Block 10.
- **D9. Both images move to the current `debian:trixie-slim`, and the aMule image to the crawler's `uv`** (Corrected: not in block 10, which left the `uv` stages to Dependabot's #637, merged to `main` on 2026-11-06 and under the whole stack: both images build on `uv` 0.13.7, the same digest). *The
  pinned base ships five fixable High CVEs across both images, four of them in `p2pwatch-amule`, the image facing
  P2P peers.* Should a Dependabot
  pull request bring them before block 10, it takes them instead (Corrected: bumped by hand to `a72b4433...` in block 10: Debian re-pushed `trixie-slim` during the lot and the 3-day cooldown held Dependabot's digest back twice). Block 10.
- **D10. Under the VPN, gluetun's control server answers only the forwarded port's read without authentication; every
  other route is closed.** *Today no route asks for authentication, which gluetun's docs strongly discourage: any
  container of the compose network, the crawler included, can stop the VPN (`PUT /v1/vpn/status` stopped a test
  tunnel); the port-sync only reads the port.* The role is written inline in the compose file, no separate file and
  no new secret, as the operator chose. Block 10.

## 4. Acceptance

Commands in appendix B.

### In tests and CI

| Check | After the lot | On main |
|---|---|---|
| A new forwarded port, in the compose smoke | amuled listens on it (TCP and UDP), its pid unchanged, amuleapi answering | amuled restarted, amuleapi gone |
| amuled killed inside `ed2k` | the container exits | s6 restarts amuled alone |
| The port-sync killed | the container exits | s6 restarts the port-sync alone |
| `restart: unless-stopped` on `ed2k` and `ed2k-gluetun`, in the deploy render test | asserted, both variants | not asserted |
| `docker compose stop ed2k` (non-regression) | amuled saves and logs `aMule shutdown completed.` | the same |
| `s6-svc -d` on amuled | the container still up 10 s later | the same |
| The port-sync's first round, amuleapi not listening yet | logged, retried at the next poll | today's restart |
| amuleapi stopped | `ed2k` `unhealthy` | `healthy` |
| The boot's `amuleapi` command line | holds no password | holds the password |
| The wxWidgets amuled runs on | 3.2.12 | 3.2.8 |
| `libssl3t64` in both images, `libpcre2-8-0` in the crawler's | `~deb13u3` | `~deb13u2` |
| The VPN variant's gluetun routes, in the deploy render test | one role, `GET /v1/portforward`, no default role | every route open |

### On the operator's node, at rc1 (umbrella)

| Check | At v5.0.0 | Today |
|---|---|---|
| A forwarded port change under the VPN | the listening port follows, amuled's pid unchanged, amuleapi answering | amuleapi gone, `ed2k` `healthy` |
| High-ID | ed2k connectable after a port change | not testable offline |
| `docker compose stop ed2k` | `aMule shutdown completed.` in amuled's log | the same |
| gluetun's control server, from the compose network | `GET /v1/portforward` answers, `PUT /v1/vpn/status` refused | both answer |
| A dead service | `RestartCount` rises, `ed2k` healthy again | s6 restarts the service alone |
| amuled's start, from `Initialising` to amuleapi listening | under `start_period` plus `interval x retries` (2 min), else `ed2k` reads `unhealthy` until then | not measured |

The umbrella's rows "amuleapi stopped inside `ed2k`" and "the port-sync killed inside `ed2k`" are held by the CI rows
above.

### What must not change

- amuled's configuration, part files and `amule.conf` as the boot reconciles them; the crawler's view of amuleapi.
- The port-sync stays off in the direct variant, and off unless `PORT_SYNC` turns it on.
- `PORT_SYNC_POLL_SECONDS` and `GLUETUN_CONTROL_URL` keep their meaning and defaults.

## 5. Blocks

| # | Branch | Change | Decisions |
|---|---|---|---|
| 10 | `fix/amule-image-upkeep` | password on stdin, Dependabot, bases, gluetun's routes | D7, D8, D9, D10 |
| 20 | `fix/amule-wxwidgets` | wxWidgets 3.2.12 in the image | D6 |
| 30 | `feat/amuleapi-health-command` | the `health` command on amuleapi | D4 |
| 40 | `feat/s6-finish-stops-container` | the healthcheck on it; a dead service restarts the container | D3, D4 |
| 50 | `feat/port-sync-live-port` | the port set live, the restart kept as fallback | D1 |
| 60 | `feat/port-sync-amuleapi-session` | the token kept, amuleapi not ready retried | D1 |
| 70 | `refactor/amuled-restart-removal` | the restart removed | D1 |
| 75 | `refactor/amule-clock-now-removal` | `MonotonicClock.now()` and `MonotonicInstant` removed (Corrected: inserted on 2026-11-06, split out of block 80 at 23 files) | |
| 80 | `feat/port-sync-reads-live-port` | the port read through amuleapi | D1 |
| 85 | `fix/amule-holistic-findings` | the holistic review's code fixes (Corrected: the closing block split for the file bound, 27 files) | |
| 90 | `docs/v5-amule-container-wrap` | closing block | |

## 6. Limits and scope

### Accepted limits

- **High-ID after a live change is unproven offline**: checked at rc1 on the operator's node, with D2's fallback.
- **The eD2k server connection is redone on a port change** (amuled reconnects so the server sees the new port): the
  crawler may see the ed2k channel briefly not `connected`.
- **A forwarded port above 65532 is refused by amuleapi**: the port-sync logs the refusal and leaves amuled on its
  port, which stays Low-ID.
- **A port-sync bug restarts amuled too** (D3, the umbrella's D24 cost): lot 4 makes the port-sync robust to its own
  errors. (Corrected: fixed by v5 lot 4's D20, every port-sync error logged and retried at the next poll)
- **A `ListenPortError` that repeats restarts the container in a loop** (Corrected: found by the holistic review,
  accepted by the operator on 2026-11-06): a route renamed or a body changed by an aMule bump (`404`, a `400` to the
  login, malformed preferences) makes the port-sync exit, the container restart, and the next round, one poll after
  amuleapi listens again, exit again. Under the VPN amuled then restarts about once a minute for good, dropping
  transfers and Kad, while `ed2k` reads `healthy` most of the time. Its signal: `docker inspect -f
  '{{.RestartCount}}' ed2k` rising, the port-sync's traceback in `docker compose logs ed2k`. Every amule-bump pull
  request runs the smoke's port-sync test against the real amuleapi; lot 4 owns the fix, with the port-sync's
  robustness. (Corrected: fixed by v5 lot 4's D20, every port-sync error logged and retried at the next poll)
- **A crashed service makes the container exit 0**, as a requested stop does: s6-svscan exits so when told to, and
  the operator keeps it simple over a script that would tell the two apart. The crash shows in the restart count and
  the `finish` log line; the umbrella's "exits in error" reads exit 0.
- **amuleapi lost alone restarts nothing** (D5).
- **wxWidgets is built by us** (D6) until Debian ships the fix; its later security releases are watched only by
  Grype on the SBOM's wx component, once the scan covers this image (umbrella D21).
- **The healthcheck's `start_period` stays 30 s**: at the operator's scale amuleapi listens only once amuled has
  loaded every part file; the rc row measures it.
- **The stop time was measured with 20 empty part files** (0.3 s): Docker's 10 s grace is kept; the rc row checks it
  at the operator's scale.

### Backlog

- New, "Postponed": **drop the wxWidgets build of the aMule image** once the Debian release it builds on ships wx
  3.2.12 or the fix: likely sid first, so trixie only through a stable backport, else the move to forky. Written in
  block 20, as the operator agreed.

### Adjacent backlog items

- **The Grype scan back on p2pwatch**: after the final tag (umbrella D21); D9 only moves the bases.
- **Contract tests for the fakes of outside systems**: the lot adds a fake amuleapi server, which that item would run
  against the real amuled; it stays open, being test debt nothing in the upgrade meets.
- The others are another lot's or after v5 (umbrella, "Adjacent backlog items").

## Appendix A. Design, block by block

Every block is written in strict TDD (workflow, Act): each new behaviour's test is written first and watched failing,
its failure line in the block report. The parts that are not Python follow the same rule through the test that
observes them: the compose smoke for the `finish` scripts and the healthcheck, the deploy render test for the
compose files, block 20's CI step for the wx build.

Every block is green alone: `dead-code-check` (vulture over every `src`) refuses a port or method whose caller lands in
a later block, so each block brings a port with its first caller and deletes what it stops calling. Sizes are
estimates on this cut (`.reviews/v5-lot1-estimate-3.md`, about 25 % either way) (Corrected: two blocks fell outside
that band: block 60, 274 lines for about 120; block 40, 173 for about 250).

### Block 10: password on stdin, Dependabot, bases, gluetun's routes (D7, D8, D9, D10)

- `.claude/CLAUDE.md` gains one line, strict TDD (write the failing test, watch it fail, then the minimal code), which
  `agents/workflow.md`'s Act cites and the measured trim (`efaf7ace`) removed; the operator's request.
- `AmuleApiAdminPasswordSetter` runs `amuleapi --config-dir=... --set-admin-pass-stdin` with the password as
  `input=` (the same stored hash as `--set-admin-pass=`, newline or not, checked at the pin).
- `.github/dependabot.yml`: the one `docker` entry over `/packages/*` becomes two, `/packages/amule` and
  `/packages/crawler`, each its own group, each with `cooldown: default-days: 0`, the operator's choice: the default
  3 days count from the tag's latest push, so each Debian re-push of `trixie-slim` restarts the wait (it held back
  the October security digest), while the caution guards against packages anyone can publish more than against
  Debian's official images.
- The five `FROM debian:trixie-slim@...` lines (amule 3, crawler 2) to the current digest (Corrected: bumped by hand to `a72b4433...` in block 10: Debian re-pushed `trixie-slim` during the lot and the 3-day cooldown held Dependabot's digest back twice); the
  aMule image's `uv` stage to the crawler's version and digest (Corrected: not in block 10, which left the `uv` stages to Dependabot's #637, merged to `main` on 2026-11-06 and under the whole stack: both images build on `uv` 0.13.7, the same digest).
- `deploy/ed2k/vpn.compose.yml`: a top-level `configs:` entry with inline `content:`, a TOML role
  `routes = ["GET /v1/portforward"]`, `auth = "none"`, mounted at `/gluetun/auth/config.toml` (gluetun's default
  `HTTP_CONTROL_SERVER_AUTH_CONFIG_FILEPATH`). `HTTP_CONTROL_SERVER_AUTH_DEFAULT_ROLE` is removed: kept, it hands
  every route the file names not to its role (`SetDefaultRole`), and `PUT /v1/vpn/status` answered `200` with both.
  Read at gluetun `v3.41.3` (`internal/server/middlewares/auth/`: a route with no role answers `401`) and run on
  `qmcgaw/gluetun:latest` (unpinned in the compose file): only `GET /v1/portforward` answered, every other route `401`.
- The deploy render test asserts the role's mount and `restart: unless-stopped` on `ed2k` and `ed2k-gluetun`, both
  variants: D3 restarts the container only through that policy, and the smoke sets none.
- About 70 lines (`.reviews/v5-lot1-estimate-2.md`).

### Block 20: wxWidgets 3.2.12 (D6)

- A build stage compiles wxWidgets 3.2.12 from its release tarball, pinned by `ADD --checksum`, without the GUI
  (`--disable-gui`: amuled needs `libwx_baseu` and `libwx_baseu_net`, amuleapi `libwx_baseu`, by `ldd` in the image)
  and with its libcurl backend, since aMule's `cmake/wx.cmake` stops unless `wxUSE_WEBREQUEST` is on; aMule builds
  against it; the runtime copies its libraries and drops Debian's
  `libwxbase3.2-1t64` (and the GTK build dependencies the stage no longer needs); the libraries land in
  `/usr/local/lib`, so the final stage runs `ldconfig` (Corrected: wx builds on Debian's regex and zlib, without XML
  so without its bundled expat; the runtime also drops `libglib2.0-0t64`, which only Debian's GTK build of wx
  pulled in, and gains `libpcre2-32-0` and wx's licence).
- `amule.cdx.json` declares the wx component with its CPE, as it declares aMule, since Syft finds no package metadata
  for it.
- `BACKLOG.md`: the "Postponed" entry of section 6.
- A CI step on the built aMule image checks that amuled resolves `libwx_baseu` from `/usr/local/lib` and that the
  library embeds `wxWidgets 3.2.12`: the file name cannot tell, 3.2.11 and 3.2.12 both being `.so.0.4.3`
  (`version.bkl`). `validate.yml` checks only aMule's version today. (Corrected: `libwx_baseu` holds no version
  string, so the step checks that `ldd` resolves both wx libraries from `/usr/local/lib` and that `amuled --version`
  reads `wxBase v<WX_VERSION>`; the closing block adds `pkg:generic/wxwidgets@<WX_VERSION>` to the SBOM checks of
  `validate.yml` and `release.yml`.)
- About 80 lines (`.reviews/v5-lot1-estimate-2.md`).

### Block 30: the `health` command on amuleapi (D4)

- A driven port for amuleapi's readiness (`ApiHealthClient`: ready when `GET http://127.0.0.1:4711/api/v1/health`
  answers `200` with `ec_connected` true; refused, timed out or `false` is not ready) (Corrected: healthy and
  unhealthy, `ApiHealthClient.is_api_healthy`, renamed in the closing block, since the port-sync's
  `ApiNotReadyError` names another state, amuleapi before its first snapshot), its adapter
  `AmuleApiHealthClient`, a fake amuleapi server in the package's tests (as `FakeGluetunControlServer`), no contract
  (the package's HTTP clients have none, as `ForwardedPortClient`). No auth; before its EC login amuleapi has no
  listener at all, so refused is the normal starting state.
- A use case behind a driving port, and `python -m p2pwatch_amule health`: exit 0 ready, 1 not. Its consumer, the
  healthcheck, is block 40's: block 30 sits at the file bound without it (`.reviews/v5-lot1-estimate-3.md`).
- About 390 lines, 15 files.

### Block 40: the healthcheck on amuleapi; a dead service restarts the container (D3, D4)

- The compose healthcheck runs block 30's command as `CMD` (tested Python, not inline code in the compose file);
  `interval 30s`, `timeout 3s`, `retries 3`, `start_period 30s` unchanged. The smoke stack's own healthcheck
  (`tests/smoke/compose.yaml`, today `s6-svstat -u`) runs it too, and `_up_until_ed2k_is_healthy`'s comment follows.
  (Corrected: the deploy render test also asserts `ed2k`'s healthcheck command.)

- `docker/services.d/amuled/finish` and `docker/services.d/port-sync/finish` (mode 0755): log the service's exit, and
  when s6 still wants it up, `exec s6-svscanctl -t /etc/services.d`. The `wantedup` guard keeps Docker's stop and
  the port-sync's own `s6-svc -d` (until block 70) from taking the container down. Proven on the image (`.reviews/v5-lot1-s6.md`): `docker stop`
  unchanged (one SIGTERM to amuled, part files saved), `docker restart` clean, `unless-stopped` restarting on exit 0.
- `.claude/rules/amule-container.md`: the `finish` scripts.
- The compose smoke, which sets no restart policy on purpose (Docker's half is block 10's render test): amuled killed
  inside `ed2k` (its pid from `/proc`) makes the container exit; after `s6-svc -d` on amuled it is still up 10 s
  later; `docker compose stop` still saves the part files. It also sees `ed2k` go `unhealthy` with amuleapi stopped
  (a SIGTERM to amuleapi, which exits 0 and is not relaunched), and `healthy` again after
  `docker compose restart ed2k`. Its IncomingDir rescan
  (`test_a_file_amuled_shares_is_recorded_completed`) moves from `s6-svc -r` to `docker compose restart ed2k`: `-r`
  now restarts the container, and `-d` then `-u` at once is the very amuleapi race D1 removes.
- The docs' s6 commands (`docs/operate.md`, `docs/troubleshooting.md`) are lot 7's: they give way to
  `docker compose restart ed2k` (umbrella D19).
- The umbrella's appendix A "Lot 1" finding, the port-sync calling s6 before `s6-supervise` listens, closes with
  block 70, which removes the port-sync's s6 calls.
- About 250 lines, 7 files.

### Block 50: the port set live, the restart kept as fallback (D1)

- A driven port for amuled's listen port through its API (`ListenPortClient.set_listen_port`), its adapter
  `AmuleApiListenPortClient` on `http://127.0.0.1:4711`: a login per call (`POST
  /api/v1/auth/login?include_token=true` with `AMULE_API_PASSWORD`), then `PATCH /api/v1/preferences
  {"connection": {"tcp_port": P, "udp_port": P}}`, one documented failure for any refusal. The fake server of block
  30 gains login and `PATCH`.
- The round: when the ports differ, `PATCH` first; on its failure, today's restart, as before this block. A first
  round before amuleapi listens therefore still restarts amuled until block 60, which the pull request names.
  (Corrected: the `PATCH` is tried on every round, inside the restart window too, only the fallback held to it;
  superseded by block 70.)
- `PortSyncSettings` gains the API password, required when the port-sync is on.
- The compose smoke's port-sync test: a TCP listener on the new port and UDP listeners on it and on port + 3 in
  `/proc/net/tcp` and `/proc/net/udp` of `ed2k`, amuled's pid unchanged, amuleapi answering (Corrected: and
  `amule.conf` holding the new port, amuled saving it itself).
- About 420 lines, 16 files.

### Block 60: the token kept, amuleapi not ready retried (D1)

- The adapter keeps its token and logs in again once on a `401`, and splits its failure in two: amuleapi not ready
  (refused, `503` before the first snapshot, a `401` after its one re-login) and a rejection (`400 bad_request` above
  65532, `400 amuled_rejected` for a port held or the EC port, amuled rolling back). (Corrected: not ready also
  covers a timeout, read or connect, at the lead's request as a fix-back, and a `503` on either route, the login's
  included; with no kept token, the first login's `401` is that one re-login. A rejection is any `400` to the
  `PATCH`.)
- The round: not ready is logged and retried at the next poll, since the first round runs at once, before amuleapi
  listens, and a propagated refusal would make the container restart in a loop under the VPN; a rejection keeps
  today's restart until block 70. Anything else propagates, the port-sync exits and block 40 restarts the container
  (Corrected: named, a refused login (`401 invalid_credentials`, `429`), a `400` to the login, any other non-2xx, a
  garbled reply, a login without a token).
  A test runs the first round against a refusing amuleapi.
- About 120 lines, 8 files.

### Block 70: the restart removed (D1)

- The fallback leaves the round: a rejection (`400`) is logged, amuled stays on its port, the next poll retries.
  Deleted with their tests, as nothing calls them any more: `is_amuled_restart_due`,
  `with_listen_port`, `ServiceSupervisor.stop_amuled` and `start_amuled` (port, s6 adapter, fake),
  `restart_min_interval` and `PORT_SYNC_RESTART_MIN_SECONDS`, the port-sync's `amule.conf` writer wiring and its
  ids, `s6-svperms` in its run script (Corrected: and the run script's wait for amuled's `supervise/control`).
- About 490 lines, 17 files, at the bound (Corrected: 520 lines, 19 files, accepted as is by the operator on 2026-11-06,
  the split through `vulture_whitelist.py` declined): `docs/high-id.md`'s variable row and `.claude/rules/amuleapi.md`'s two stale
  facts (amuled does not flush `amule.conf` on exit; a token survives an amuleapi restart, the boot's password reset
  invalidating it) go to the closing block. Should the measured block still pass a bound, the only green split
  bridges two names through `vulture_whitelist.py` (`.reviews/v5-lot1-estimate-3.md`, 60a and 60b): the lead asks the
  operator first.

### Block 75: `MonotonicClock.now()` and `MonotonicInstant` removed

(Corrected: inserted on 2026-11-06, a class 2 the operator accepted.) No `src` of `p2pwatch_amule` reads `now` once
block 70 removes the restart floor; vulture misses it, the crawler having a `.now`. Written in block 80, which then
passed the file bound (23 files), and split out along its commit: 127 lines, 9 files. The clock contract states
`sleep`'s promise through an `elapsed_during` fixture each implementation supplies.

### Block 80: the port read through amuleapi (D1)

- `ListenPortClient.read_listen_port` (`GET /api/v1/preferences`, `connection.tcp_port`), the round comparing on it;
  `tcp_listen_port` and the port-sync's `amule.conf` reader deleted. The port-sync then reads no file of amuled's.
  The read's failures (refused, `503` before the first snapshot, a `401` after its one re-login) are logged and
  retried at the next poll, as the `PATCH`'s. (Corrected: a timeout too, as block 60's; a `400` to the read
  propagates, not a rejection; preferences without an integer `connection.tcp_port`, a JSON `true` included,
  propagate as `ListenPortError`.)
- About 270 lines, 13 files (Corrected: 316 lines, 15 files, the clock removal split out as block 75).

### Block 85: the holistic review's code fixes

(Corrected: the closing block split for the file bound on 2026-11-06, at 141 lines and 27 files.) The code half of
the holistic findings: the command line takes amuleapi's URL so no unit test binds port 4711, the health side renamed
healthy, the refusal bodies cut once, the dead `rstrip` and whitelist line removed, wx asserted in the SBOM checks.
95 lines, 19 files.

### Block 90: closing

- The holistic review's findings, `BACKLOG.md`, the handoff (workflow, Wrap); `docs/high-id.md`'s variable row and
  `.claude/rules/amuleapi.md`'s two stale facts (block 70). (Corrected: the records only, the code fixes being
  block 85's: 46 lines, 8 files.)

## Appendix B. Acceptance, in detail

| Row | Command, and the output that fails it |
|---|---|
| Forwarded port in the smoke | `compose_integration`'s port-sync test: fails unless the listeners on the new port and port + 3 appear, or if amuled's pid changes, or if `/api/v1/health` stops answering |
| amuled killed | `docker compose exec ed2k sh -c 'kill -KILL <amuled pid from /proc>'`, then the container's state: fails if it stays running, or if the log lacks the `finish amuled` line reading `wantedup true` |
| Port-sync killed | the same on the port-sync's pid, the port-sync started with `s6-svc -u` as the smoke does today |
| Restart policy | the deploy render test: fails if `ed2k` or `ed2k-gluetun` lacks `restart: unless-stopped` in either variant |
| Docker's stop | `docker compose stop ed2k`, then amuled's logfile: fails without `aMule shutdown completed.` |
| `s6-svc -d` | `docker compose exec ed2k s6-svc -d /etc/services.d/amuled`, then the state 10 s later: fails if the container has exited |
| First round | a lifecycle test, amuleapi refusing: fails if the port-sync raises or restarts amuled |
| amuleapi stopped | SIGTERM to amuleapi, then `docker inspect` health: fails if it stays `healthy` past `interval x retries` |
| Password on stdin | the adapter's test: fails if the argv given to `run_command` contains the password, or if `input` does not carry it; the smoke's core logs in with it |
| wxWidgets | block 20's CI step on the built image: fails unless `ldd` resolves `libwx_baseu` from `/usr/local/lib` and the library embeds `wxWidgets 3.2.12` (Corrected: unless `ldd` resolves both wx libraries from `/usr/local/lib` and `amuled --version` reads `wxBase v<WX_VERSION>`) |
| gluetun's routes | the deploy render test reads the inline role; at rc1, from `p2pwatch`, `GET http://ed2k:8000/v1/portforward` answers and `PUT http://ed2k:8000/v1/vpn/status` gets `401`: fails if the `PUT` is accepted |
| Debian packages | `docker run --rm --entrypoint dpkg-query <image> -W libssl3t64 libpcre2-8-0` on both images: fails on `~deb13u2` (the aMule image already ships `libpcre2-8-0` at `~deb13u3` on `main`) |
| Dependabot | after block 10 merges, a Dependabot job "docker in /packages/amule" in the repository's Dependabot runs: fails if none appears in the next weekly run |
| Dead service at rc | the amuled row on the node: `docker inspect -f '{{.RestartCount}}' ed2k` rises and `ed2k` turns healthy again |
| amuled's start at rc | amuled's logfile on the node, `Initialising` to `amuleapi running on pid`: fails past 2 min |
| rc rows | umbrella appendix C |

## Appendix C. Facts, 2026-11-04 and 2026-11-05

Probes by named teammates, reports in `.reviews/v5-lot1-probe.md`, `v5-lot1-s6.md`, `v5-lot1-dependabot.md`,
`v5-lot1-spec.md` and `v5-lot1-spec-2.md` (the spec reviews), `v5-lot1-offshelf.md` and `v5-lot1-glueforward.md` (the option set aside);
source read at the aMule pin `0db738ed`; runs on `p2pwatch-amule:v5audit` (`main`'s `packages/amule`), Docker
Desktop, an internal network, 20 part files.

| Fact | Result |
|---|---|
| `GET /api/v1/health` | no auth; `200` with `ec_connected`, `snapshot_ready` while serving; no listener before amuleapi's EC login (`App.cpp:603-627`) |
| Login | `POST /api/v1/auth/login?include_token=true`; 24 h token, no refresh, re-login on `401`; 5 failures in 60 s lock the client's IP out for 300 s |
| `PATCH` the ports | `200` in 3 ms; TCP, client UDP and server UDP (TCP + 3) rebound; both pids unchanged; `amule.conf` saved by amuled; on a TCP port change amuled reconnects to an eD2k server (`amule.cpp:1876-1879`); a held port or the EC port `400 amuled_rejected` with the old ports kept; 65533 `400 bad_request` |
| amuled on exit | does not write `amule.conf` (a port written while it ran survived a clean stop); saves part files, logs `aMule shutdown completed.`, exits 0 in 0.17 to 0.24 s on SIGTERM; a second SIGTERM kills it unsaved |
| amuleapi's exits | `1` on EC loss (relaunched by amuled after 5 s, doubling to 60 s); `0` on SIGTERM, a bind failure or an EC login failure (never relaunched) |
| s6 `finish` with `s6-svscanctl -t` | amuled or the port-sync SIGKILLed: the container exits 0 (no `.s6-svscan/finish` yet), restarted by `unless-stopped` after 0.13 s; `docker stop` 0.31 s, one SIGTERM to amuled, part files saved; `docker restart` clean; without the `wantedup` guard `s6-svc -d` would restart the container |
| wxWidgets | Debian trixie 3.2.8, sid 3.2.11, Ubuntu 26.04 3.2.9 and 26.10 3.2.11, Alpine 3.24 and edge 3.2.9, Fedora 45 3.2.11: none with the fix (`3382306c8`, in 3.2.12); rawhide and Arch 3.2.12 but no `s6`, Arch amd64 only |
| Dependabot | jobs for `/packages/*` log "Deferring creation of a new pull request" and update only the directories an open group pull request lists; no job ever targeted `/packages/amule` |
| Current bases | `debian:trixie-slim@sha256:f6b08b09...` (Corrected: bumped by hand to `a72b4433...` in block 10: Debian re-pushed `trixie-slim` during the lot and the 3-day cooldown held Dependabot's digest back twice) (`libssl3t64 3.5.7-1~deb13u3`, `libpcre2-8-0 10.46-1~deb13u3`); pinned: `libssl3t64` `~deb13u2` in both images, `libpcre2-8-0` `~deb13u2` in the crawler's only |
| Fixable High CVEs | Grype `v0.121.0 --only-fixed` on `docker save` archives: five over both images, four in `p2pwatch-amule` (`CVE-2026-84782`, `-54873`, `-84784`, `-72897`, `libssl3t64`), five in `p2pwatch` (the same and `CVE-2026-103111`, `libpcre2-8-0`) |
| gluetun's roles | read at `v3.41.3`: a route with no role answers `401`; the file at `/gluetun/auth/config.toml` by default; `SetDefaultRole` gives the default role every route no file role names. Run on `qmcgaw/gluetun:latest` with the inline `configs:` entry: `read 1 roles from authentication file`, `GET /v1/portforward` `200`, five other routes `401`; with the env default role kept, `PUT /v1/vpn/status` `200` |
| wx libraries | amuled links `libwx_baseu` and `libwx_baseu_net`, amuleapi `libwx_baseu`; aMule's `cmake/wx.cmake` requires `wxUSE_WEBREQUEST`; 3.2.11 and 3.2.12 share the library version `0.4.3`, 3.2.8 is `0.4.1` |
| `--set-admin-pass-stdin` | stores the same hash as `--set-admin-pass=`, with or without a trailing newline |
