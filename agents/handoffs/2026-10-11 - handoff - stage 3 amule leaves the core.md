# Handoff: stage 3, aMule leaves the core, renamed p2pwatch

Drafted by block 120, corrected by the closing block 130.

## State

Tier Spec lot, spec `agents/specs/2026-10-10-stage3-amule-leaves-the-core.md` (approved 2026-10-11).
Fifteen blocks. Block 10 (#157, `refactor/rename-p2pwatch`) was merged alone, cut from `main` at
`30fc074`; the operator then renamed the repository to `mission-titar/p2pwatch`, the lead ran
`git remote set-url` and reset the stale `.git/gh-stack` state the rename left. The rest is a stack
cut from the new `main`: #159, #162, #164 to #174, then the closing block 130
(`docs/stage3-closing`).

The holistic review ran over `git diff 30fc074...origin/docs/stage3-contributor-docs`, not over the
merge base with `main`, so it read the rename too (D1).

Nothing of the stack is merged and no release follows (Non-goals; stage 1's D16): the node pulls
`latest`, which stays on `mulewatch` 4.1.0. `git tag -l 'v*'` still ends at `v4.1.0`. Neither
database changes schema in this lot.

A node is now two images, two containers: the core `p2pwatch` (crawler and webui, no s6, run as
`PUID:PGID`, restarted by Docker) and `p2pwatch-amule`, compose service `ed2k` (s6: amuled, which
starts amuleapi, and port-sync). The core reaches amuleapi at `ed2k:4711` in both variants.

## What was built

- **The rename** (block 10): package, dist, image, compose project, `P2PWATCH_TEST_API_*`, docs site,
  VEX `@id`, apprise identity, webui titles, living docs. The `file_id` namespace URL became
  `https://mission-titar.github.io/p2pwatch/file` (UUID `d30da1ca-776a-5106-b046-daf77302c1af`): no
  production catalog carried one yet, and it can never change after the next release. Kept on
  purpose: `docs/migration-1x.md`, `migration-2x.md`, `troubleshooting-start.md`, `verify-image.md`,
  and from block 110 `migration-4x.md`.
- **`packages/amule/`** (block 20): workspace member `p2pwatch-amule`, package `p2pwatch_amule`,
  stdlib only, under the gate (own pytest at 100 %, root ruff and `mypy --strict`). The boot step
  moved in unchanged as `p2pwatch_amule.config`.
- **Port-sync's parts** (block 30): `amule.conf`'s `Port` / `UDPPort` read and written through the
  boot step's case-sensitive, non-interpolating parser; gluetun's `/v1/portforward` over
  `urllib.request` (10 s, defensive parse); the four variables with defaults (`PORT_SYNC` off,
  `GLUETUN_CONTROL_URL` `http://localhost:8000`, 60 s, 300 s). `PORT_SYNC` takes gluetun's eight
  boolean spellings, any case. The boot step validates the three others only when it is on.
- **Port-sync's loop and s6 service** (block 35): `-wD -T 60000 -d`, the write only on exit 0,
  `-u` in a `finally`, a `-u` at start; the write is atomic (temporary file + `os.replace`, `0600`)
  and starts from the file read after the stop. An `amule.conf` that cannot be opened (block 130)
  or parsed, or a non-numeric `Port`, is logged and touches nothing, retried next round. The run
  script grants `s6-svperms -G amule -E amule` on amuled, then drops to `amule`. The boot step
  creates or removes `services.d/port-sync/down`. Its logger is `p2pwatch_amule.port_sync`.
- **The core loses port-sync** (blocks 40 to 65): composition unwired, `port_sync` refused by name
  (`crawler: key 'port_sync' was removed, delete it from crawler.yml`), `PORT_SYNC:
  ${VPN_PORT_FORWARDING:-off}` in the VPN stack; then the loop, its adapters and ports, its three
  events, their policy arms and metrics (`emule_port_sync_triggered`, `emule_port_mismatch`,
  `emule_high_id_recovered`), and `get_listen_port` / `set_listen_port` deleted with their tests and
  `test_amuled_preferences.py`. `EdgeState` stays (the download loop's `disk_low`).
- **The `p2pwatch-amule` image** (block 70): aMule's build stage, a Python stage with only
  `p2pwatch-amule`, Debian runtime with s6; entrypoint runs the boot step then `s6-svscan`. The
  three integration suites run against it alone (`PUID`, `PGID`, both passwords, no config mount).
- **The core image without aMule** (block 80): Python and the venv, `CMD python -m p2pwatch ...`, no
  entrypoint, no s6. `AMULE_API_HOST = "ed2k"`. The smoke stack builds and runs both images; the
  core runs as `user: PUID:PGID` with `/downloads` read-only. `amule-bump` and CI's pin read point
  at `packages/amule/Dockerfile`. Since block 130, `validate.yml` checks on both arches that the core
  image holds none of `amuled`, `amuleapi`, `s6-svscan`.
- **The include layout** (block 90): `deploy/compose.yml` (core + one `include:`),
  `deploy/ed2k/{service,direct,vpn}.compose.yml`; `ed2k-gluetun` carries the alias `ed2k`; the
  direct variant publishes `4672/udp` (Kad) instead of `4662/udp`; no `depends_on` between core and
  `ed2k`. The smoke suite renders both variants from a temporary copy with its own `.env`, and
  since block 130 asserts each variant's published ports and the `.env` claim in isolation.
- **Two images published and scanned** (block 100): `publish-manifest` and `grype-scan.yml` are a
  matrix over `crawler` and `amule`; one VEX per image (`security/amule.vex.openvex.json` holds the
  two aMule claims and the two Python ones); `vex_files()` maps both; `validate.yml` uploads
  `digest-<package>-<arch>`.
- **Docs** (blocks 110, 120): `docs/migration-4x.md` and the living operator pages (110);
  troubleshooting, contributor pages, `SECURITY.md` and `AGENTS.md` (120).

## Decisions taken during Act

- **Class 2, block 10**: three files cited historical `mulewatch` names that D1's table did not
  list. Operator: option 2. The `mulewatch-crawler` paragraphs were deleted (`SECURITY.md`,
  `verify-image.md`), and `troubleshooting-start.md` and `verify-image.md` joined D1's table with a
  `(Corrected: ...)` marker.
- **Fix-back, block 30 (operator's review)**: the operator's rule, "data read from the environment
  is validated early, a rejection names the variable". `GLUETUN_CONTROL_URL` is fully parsed (a
  malformed host or a port outside 1-65535 exits naming it); both passwords refuse any Unicode `Cc`
  character. The 12-character EC password minimum `install.md` claimed does not exist in aMule at
  `909d304`: the doc was corrected, no rule added.
- **Fix-back, block 35 (asked by the lead)**: a non-numeric `[eMule] Port` or a `configparser.Error`
  is absorbed (logged, no s6 command, retried next round), per the boundary discipline.
- **Block 30**: the two intervals are positive **integers** (D5 says "positive"); an empty variable
  takes its default, like an unset one.
- **Block 35**: the atomic write and `CONFIG_DIR` moved to `config/conf.py`; the smoke test's
  "disabled port-sync stays down" landed here rather than in block 80.
- **Block 50**: `ports/port_forwarding.py` left here, not in block 60: once the loop went, nothing
  imported it and the coverage gate failed on it.
- **Block 80**: the ownership check reads `stat` inside the core container (Docker Desktop shows every
  bind-mounted file as the host user's).
- **Block 90**: the render test copies only `deploy/**/*compose.yml`, not all of `deploy/` (D11), so a
  developer's `deploy/.env` and `data/` are never copied.
- **Block 100**: `validate.yml` edited too (aMule build pushes when `inputs.push`, two digest
  artifacts); the new VEX is version 1, the crawler VEX goes 6 to 7.
- **Block 110**: `index.md` and `legal.md` fixed as class 1 (they described one container);
  `docker compose exec --user amule p2pwatch ... merge` dropped its `--user` (the core image has no
  `amule` user).
- **Block 120**: class 1 fixes. The documented `validate-config` command never worked in the image:
  its defaults are `deploy/*.yml` relative to `/app` (`Invalid config: unreadable YAML file:
  deploy/crawler.yml`); `troubleshooting.md` and `operate.md` now use
  `docker compose run --rm p2pwatch python -m p2pwatch validate-config --config /app/config/...`,
  which also works while the core loops. The manual `local.db` write uses
  `docker compose stop` / `run --rm` / `start` (no s6 nor `amule` user in the core). The
  `file_observation_ranges` remedy points at `migration-4x.md`'s rollback instead of pinning an
  image in the removed `base.compose.yml`. The integration suites' skip message named the core
  image; it now builds `p2pwatch-amule` from the tree. `testing.md`'s "never run" note of 2026-09-16
  and `troubleshooting-start.md`'s `EcAuthError` cause went (both obsolete). `AGENTS.md`'s em dashes
  went with its rewrite.
- **Block 130, `PORT_FORWARD_ONLY`**: the operator decided to couple
  `PORT_FORWARD_ONLY: ${VPN_PORT_FORWARDING:-off}` on `ed2k-gluetun`, then reversed it (option 1):
  gluetun's `internal/configuration/settings/serverselection.go` (v3.41.3 and `master`) already
  defaults it on when `VPN_PORT_FORWARDING` is on and the provider is Proton or PIA (l.347-349), and
  refuses to start when it is set on with any other provider (l.280-282), PrivateVPN and Perfect
  Privacy included. No compose sets it; `docs/high-id.md` says there is nothing to set.

## Spec corrections

Applied by block 130, each with a `(Corrected: ...)` marker at the place concerned, each checked
against git (`git show --stat` of the block's commit, `git ls-tree` of `4501cda` for the s6 names):

- Section 6, "The core image holds no aMule": dash's `command -v a b c` checks only the first name
  (`command -v nonexistent amuled s6-svscan` printed nothing, rc 127, in `p2pwatch-amule`); one run
  per name, now a `validate.yml` step.
- "Transient states inside the stack": from block 80 to block 90, `deploy/base.compose.yml` ran the
  core image, healthchecked on `s6-svstat`, without aMule nor s6 (unlisted).
- Block 100's contents: `validate.yml` too (`50f9aee`).
- Blocks 50 and 60's contents: block 50 removed `ports/port_forwarding.py` (`5719555`).
- Blocks 70 and 80's contents: the crawler's s6 service was `services.d/p2pwatch` after block 10.
- Section 4's second claim and section 6's render: the isolating `AMULE_EC_PASSWORD` case, and the
  published ports.
- D4 (atomic write, block 35), D5 (positive integers, empty means default, block 30), D11 (only the
  compose files are copied, block 90).
- D5: `docs/high-id.md` told the operator to keep a `PORT_FORWARD_ONLY` no compose set; the
  operator's coupling and its reversal.

## Wrap counts

- **Fix-backs during Act: 2.** Block 30: the operator's early environment validation. Block 35: the
  absorption of a non-numeric `Port` and a `configparser.Error`, committed after rebasing onto block
  30's fix.
- **Fix-backs after the operator's review of the stack, in 5 blocks**: 30 (gluetun's port must be an
  `int` in 1-65535; an empty `PORT_SYNC` handled before the lookup), 35 (`port_sync/__main__.py`'s
  names: `sync_listen_port_once`, `_signal_amuled`, `_write_listen_port`, `AMULED_SERVICE_DIR`), 70,
  80 twice (the second an `amule_bump` test rename) and 90 (comments trimmed).
- **Cascaded rebases: 2.** During Act, after block 30's fix-back, `gh stack rebase --upstack` stopped
  on a conflict in block 35 (`config/__main__.py`, `test_config_main.py`, both sides kept); the lead
  aborted it, block 35's teammate rebased its branch onto the new block 30, then the cascade resumed.
  Blocks 40 and up did not exist yet. After the review, one cascade with 3 conflicts, each aborted
  and resolved by the branch's teammate: blocks 80 and 100 on `validate.yml`'s comment, block 130 on
  `port_sync/__main__.py` (the new names kept, with block 130's `OSError` absorption and logger).
- **Runs re-triggered: 17, for 15 blocks.** During Act, 3: `feat/amule-port-sync-parts` once
  (`5c0c540`), `feat/amule-port-sync-loop` twice (`fdbaa4e`, one of the two a cancelled duplicate);
  every other branch ran once. Command, per stack branch: `gh run list --branch <b> --workflow
  pr.yml --json headSha,event,conclusion,createdAt`; `--workflow validate.yml` prints nothing, it is
  the reusable workflow `pr.yml` calls. After the review, the push of the rebased stack re-ran 13 of
  the 14 open pull requests once (`refactor/amule-package` did not move), and this count's own
  correction re-ran #175 once: 3 + 13 + 1 = 17. More runs than blocks: by the workflow's measure,
  this lot's stacking cost more than pull requests in series, all of the excess from the review's
  fix-backs.
- **Bodies the operator called unreadable: none.**
- **Friction**: the repository rename left `.git/gh-stack` stale and the lead reset it; the spec
  reviewer could not be launched from a fork.

## Holistic review

`.reviews/stage3-holistic.md` (gitignored), over
`git diff 30fc074...origin/docs/stage3-contributor-docs`: CRITICAL 0, MAJOR 1, MINOR 11. Every
finding was fixed in block 130.

| # | Finding | Exit |
|---|---|---|
| 1 | MAJOR: section 6's port-sync grep printed the `AMULE_API_HOST` comment naming `ed2k-gluetun` | Fixed: comment reworded; the grep prints only `"port_sync",` |
| 2 | The `.env` claim had no isolating failing case | Fixed: `ed2k`'s `AMULE_EC_PASSWORD` asserted; dropped from the `.env`, the render fails with `required variable AMULE_EC_PASSWORD is missing a value` |
| 3 | `operate.md`: a manual `-d` on amuled does not hold under port-sync | Fixed: stop port-sync first |
| 4 | Port-sync crashed on an `amule.conf` it cannot open | Fixed (TDD): `OSError` absorbed like a parse error; the missing-file case failed with `FileNotFoundError` first |
| 5 | Port-sync logged as `__main__` | Fixed: `p2pwatch_amule.port_sync` |
| 6 | The tunnel remedy restarted amuled after a `.env` edit | Fixed: `up -d --force-recreate ed2k-gluetun ed2k` in `troubleshooting.md` and `troubleshooting-start.md` |
| 7 | D10's published ports untested | Fixed: asserted per variant; a temporary `4662/udp` failed it |
| 8 | "The core image holds no aMule" had no automated check | Fixed: a `validate.yml` step; its loop exits 1 on `amuled` against the aMule image, 0 against the core |
| 9 | Comments still described one container | Fixed |
| 10 | Comments deferring to decision ids | Fixed |
| 11 | Review mandates named moved paths and `mulewatch` | Fixed |
| 12 | Two handoff statements | Fixed in this handoff |

## Pitfalls

- **dash's `command -v a b c` prints only the first name**: loop over the names.
- **Docker Desktop shows every bind-mounted file as the host user's**: an ownership check must read
  `stat` inside the container.
- **s6 gives event subscription to root's group only**: without `-E`, `s6-svc -wD` exits 111 and
  sends nothing, amuled stays up. `-G` after `-G -E` keeps `events: group amule`. `s6-svperms` with no
  option prints three lines per service; the smoke test waits on that exact output.
- **`extends:` in an included file resolves `file:` and relative binds against the included file's
  directory**, and never carries `depends_on` over.
- **A positive render assertion can pass for the wrong reason**: `PUID` is interpolated by both the
  core and `ed2k`, so removing it fails on the core first. Isolate with a variable only the included
  file reads (`AMULE_EC_PASSWORD`).
- **The crawler's `validate-config` defaults are relative `deploy/*.yml`**: in the image, pass the
  three `/app/config/` paths.
- **`docker compose run --rm p2pwatch ...`** is the one-off tool for the core: same image, user and
  mounts, no ports, no dependencies.
- **A removed-key test matching only the key name passes against any error that quotes the key**:
  match "was removed".
- **Removing a module's last importer leaves its port uncovered**, and the per-package gate fails.
- **A comment can break an acceptance grep**: section 6's grep caught block 80's comment only at
  Wrap. Re-run the lot's acceptance greps at the top of the stack.
- **Test basenames must stay unique across the non-crawler `tests/` directories** (flat modules for
  mypy): `test_config_main.py`, not `test_main.py`.
- **A mutation restored within the same second, at the same size, leaves a stale `.pyc`**: delete
  `__pycache__` before believing the result (blocks 30 and 90).
- **The live node publishes 4711 and 8080 on the dev machine**: a test daemon goes on another host
  port (`P2PWATCH_TEST_API_PORT`).
- **Zensical slugs ` : ` to `--`** in heading anchors.
- **The build step id is `amule-image`** in `validate.yml`, since `amule` reads the pin. A matrix
  job's `needs` waits for every leg.
- **`gh run list --workflow validate.yml` is empty**: pull requests run `pr.yml`, which calls it.
- **The integration suites run locally, Docker Desktop included** (6 passed against
  `p2pwatch-amule` on 2026-10-11, blocks 70 and 120); only the compose smoke's completion test fails
  under Desktop (bind mount, SQLite `-shm`), and CI is authoritative for it.
- **gluetun turns `PORT_FORWARD_ONLY` on by itself** for Proton and PIA when `VPN_PORT_FORWARDING`
  is on, and refuses it set on with any other provider.

## Not validated

- **Port-sync against a real gluetun and Proton**: a forwarded port read, amuled stopped, both ports
  written, amuled restarted, High-ID within the restart window. Only the fakes and the s6 rights
  check on a real container are tested.
- **The vpn variant end to end on the node**: the core reading `amuled` through `ed2k-gluetun`'s
  alias, `FIREWALL_INPUT_PORTS=4711`. Only its `docker compose config` render is tested.
- **The node's `crawler.yml` must lose `port_sync:` and the five stage 2 keys before any future image
  pull** (`cycle_interval_seconds`, `search_poll_budget_seconds`, `search_poll_interval_seconds`,
  `keyword_pause_min_seconds`, `keyword_pause_max_seconds`, previous handoff): the core refuses each
  with a `ConfigError`. `docs/migration-4x.md` covers it.
- **The first `main` push after the merge**: both images pushed, the per-image matrix legs,
  `cosign verify` and `cosign verify-attestation --type openvex` on `p2pwatch:main` and
  `p2pwatch-amule:main`, and `docker buildx imagetools inspect` listing `linux/amd64` and
  `linux/arm64` for each. The new "core image holds no aMule" step on arm64.
- **GHCR package visibility** of `p2pwatch` and `p2pwatch-amule`, created by that push with the
  organization's default: `gh api /orgs/mission-titar/packages/container/<name> -q .visibility`.
- **The daily Grype scan fails until the first p2pwatch release**: it scans `latest` of both images,
  which do not exist yet (D13).
- **amuled's stop time under s6**, against the 60 s down timeout: `time s6-svc -wD -d
  /etc/services.d/amuled` in `ed2k` on the node.
- A port-sync restart as the core sees it (unreachable, alert after 2 min), unmeasured.
- `docs/migration-4x.md`'s commands and rollback on a real 4.x node.
- Whether `mission-titar.github.io/mulewatch/` redirects after the rename.
- The per-container `mem_limit: 2g` and `pids_limit: 512`, and `no-new-privileges` with `setpriv`, on
  a real node.
- arm64: CI only.

## Next

The operator reviews the stack, the lead rebases it onto `main`, and the operator merges. **No
release is proposed** (stage 1's D16: none before the first new network). Then stage 4 or stage 5
per `BACKLOG.md`. Stage 5's line now carries the free-space check per client output directory
(D10: the core's disk floor reads `ed2k`'s only), added with the operator's agreement.

**At the first p2pwatch release**: remove the "Pas encore de version p2pwatch publiée" warning at
the top of `docs/install.md`; the daily Grype scan stops failing. The node migrates by
`docs/migration-4x.md`, which also drops `port_sync:` and the five stage 2 keys its `crawler.yml`
still carries, and whoever cuts the release tells the operator first.
