# Handoff: the five other hexagons, lot 3b of the hexagonal architecture umbrella

Drafted by block 59 from the lot's block reports (#344, #345, #347 to #356) and its own, corrected by the closing
block 60 with the holistic review (`.reviews/lot3b-holistic.md`, gitignored).

## State

Tier Spec lot. Spec `agents/specs/2026-10-20-five-hexagons.md` (approved 2026-10-20), its 3b table re-measured on
`main` at `b48391b` after 3a merged (`.reviews/lot3b-estimate.md`, gitignored) and re-cut with the operator. It
carries out the aMule container's part of lot 3 of the umbrella spec
`agents/specs/2026-10-18-hexagonal-architecture.md`. Lot 3c (the three checking tools, the rule, the
documentation) follows.

One stack cut from `main` at `b48391b` (gh stack #346). Thirteen blocks: the spec's eleven rows 40 to 58 and 59,
row 56 split into 56 and 57, then the closing block 60.

| Block | Pull request | Branch |
|---|---|---|
| 40 | #344 | `feat/boot-container-accounts` |
| 42 | #345 | `feat/boot-mount-points` |
| 44 | #347 | `feat/boot-amule-conf` |
| 46 | #348 | `feat/boot-admin-password` |
| 48 | #349 | `feat/boot-down-file` |
| 50 | #350 | `refactor/port-sync-monotonic-clock` |
| 52 | #351 | `refactor/port-sync-decision-and-logger` |
| 54 | #352 | `refactor/port-sync-gluetun-reader` |
| 56 | #353 | `feat/port-sync-loop` |
| 57 | #354 | `feat/port-sync-loop-use-case` |
| 58 | #355 | `refactor/port-sync-runner-wired` |
| 59 | #356 | `test/port-sync-smoke` |
| 60 | (this block) | `docs/five-hexagons-3b-wrap` |

Nothing of the stack is merged. The lot changes the aMule image's Python, so a release is possible after the
merge, but not before the backlog's "A copy before a migration that rewrites rows" ships (spec, "Backlog").

## What was built

- **The boot step, a use case** (blocks 40 to 48): `BootContainer` behind `ContainerBooter.boot_container(env)`
  refuses the first bad variable before any change, then runs the boot's steps in their order, each through a
  driven port: `AccountManager` (`PosixAccountManager`: `groupadd`, `useradd`), `AmuledDirectoryPreparer`
  (`PosixAmuledDirectoryPreparer`: the home, `.aMule` and the two mount points, chowned, never recursively),
  `AmuleConfReader`/`AmuleConfWriter` (`PosixAmuleConf`: a 0600 temporary file created afresh, chowned, then
  `os.replace`, removed when a step raises), `AdminPasswordSetter` (`AmuleApiAdminPasswordSetter`: `amuleapi
  --set-admin-pass` as `PUID:PGID` with no supplementary group) and `ServiceSupervisor` (`S6ServiceSupervisor`:
  port-sync's `down` file). Each adapter receives from `__main__` what it drives (C2): paths, `subprocess.run`,
  `os.chown`, `grp.getgrnam`, `pwd.getpwnam`. `boot.py` and `test_boot.py` are gone. One unit test pins the
  boot's whole order, its fakes recording into one action list.
- **Port-sync, a use case** (blocks 50 to 58, reshaped by 60): `RunPortSyncLoop`, port-sync's root behind no port
  as `RunCrawler` is the crawler's, on `MonotonicClock` (`SystemMonotonicClock`, this hexagon's own copy with a
  `MonotonicInstant` that keeps only the difference of two instants), `Logger` (`StdlibLogger` under the two names
  `docs/migration-4x.md` documents), `ForwardedPortReader` (`GluetunForwardedPortReader`, gluetun's URL, timeout
  and URL opener from the composition), the boot's `AmuleConfReader`/`AmuleConfWriter` and `ServiceSupervisor`
  (`stop_amuled() -> bool`, `start_amuled()`). The decision is the domain's
  `is_amuled_restart_due(forwarded_port, listen_port, ...)`; `PortSyncSettings` carries `timedelta`s and
  `PUID`/`PGID`, the owner of the rewritten `amule.conf`. `PortSyncApp(PortSyncLoopRunner)`, in `composition/`,
  holds `env` from its constructor as `CrawlerApp` does, parses the variables when called and assembles the loop;
  the command line receives it as `port_sync_loop_runner` (D4) and keeps `env` for `boot_container(env)`.
  `port_sync.py` and `gluetun.py` are gone.
- **The clock rule** (block 50): `packages/amule/`'s `TID251` exemption is gone, `banned-api` bans `time.sleep`,
  and only `system_monotonic_clock.py` is exempt; `AGENTS.md`'s rule says so.
- **The compose smoke runs port-sync's restart path** (block 59): a stand-in for gluetun's `/v1/portforward`, a
  static file served by `python -m http.server` on `ed2k`'s own `localhost:8000` (port-sync's default URL, as in
  the vpn variant where `ed2k` shares gluetun's network namespace). Serving the port amuled listens on (4662)
  leaves `amule.conf` and amuled's pid alone over two rounds; serving 40123 rewrites `Port` and `UDPPort` and
  restarts amuled. The smoke stack sets `PORT_SYNC_POLL_SECONDS: "1"`.
- **`AGENTS.md`**: the hexagonal rule and the glossary's `use case` name both roots (`RunCrawler`,
  `RunPortSyncLoop`); the port-sync row names `PortSyncApp` behind the port; C1 and C2 leave only `vex_checks`
  and `coverage_checks` for lot 3c.

## What an operator sees change

Nothing in the aMule container's variables, values when unset, refusal messages, exit codes, log lines or logger
names. Narrowed behaviours:

- A conf the boot cannot read stops it on the read rather than on the write (block 44).
- The boot writes `amule.conf` through `amule.conf.tmp` and `os.replace`, where it wrote in place then ran
  `chmod 0600`; port-sync's temporary file is `amule.conf.tmp` too, where it was `amule.conf.port-sync` (blocks
  44, 56). The 0600 mode comes from the temporary file's creation, so a umask would narrow it (none is set
  anywhere); a leftover temporary file is removed first, and one a failed write leaves is removed (block 60).
- Port-sync refuses an unset `PUID` or `PGID` (block 56), which the boot refuses first.
- A missing `amule.conf` in port-sync's round logs `amule.conf does not exist` instead of `open`'s errno text, the
  format string unchanged (block 56).

## Acceptance

3b meets 6, 12, 9 and 10, and 1, 3 and 4 for `p2pwatch_amule`. Re-run by block 60 on 2026-10-21 unless noted.

1. `git grep -nE "monkeypatch|MonkeyPatch|mock\.patch|from unittest\.mock import.*patch" -- '*.py'` prints 29 lines,
   all in `vex_checks` (23) and `coverage_checks` (6), for 3c; none in `packages/amule`.
3. `grep -c "deprecated = true" tach.toml` prints 14 (19 on the umbrella's `main`, 15 at 3a's top), none on a
   `p2pwatch_amule` module; a `tomllib` pass (block 59) finds adapter-to-adapter edges only in `vex_checks` and
   `coverage_checks`.
4. `grep -rn "^def main" packages/*/src`: `p2pwatch_amule` has only its `__main__.py`'s; 7 others remain in
   `vex_checks`, `template_checks` and `coverage_checks`.
6. The spec's `git grep -hE "sys.exit|_logger\.(info|warning|error)|logger\.(info|warning|error)"` over
   `packages/amule/src`, plus `SettingsError(`, prefixes normalised and sorted (block 59): the same format strings
   and refusal messages on `main` and at the top; the top adds `StdlibLogger`'s three generic forwards, and
   arguments are renamed (`stderr`, `forwarded_port`, `listen_port`). Block 60's renames leave the format strings
   unchanged (11 quoted strings, identical against block 59). Block 48 compared 10 refusal cases at runtime under
   `env -i`: identical stderr and exit 1. CI's compose smoke and the api, download and orchestration suites
   against `p2pwatch-amule` on amd64 and arm64: green at every block's head; block 59's run 39614336152 is green
   on both arches, compose smoke 8 passed and 1 skipped (the new restart case included), the api, download and
   orchestration suites 6 passed.
9. `git diff --stat` over `deploy`, `security`, the crawler's `migrations`, `packages/amule/docker`,
   `packages/amule/Dockerfile` and `.github/workflows` prints nothing, from `main` to block 59 (block 59) and from
   59 to 60; the 8 environment variable names under `packages/amule/src` are the same on `main` and at the top.
10. The gate green at every block (each report).
12. Block 59 locally, Docker Desktop: `test_port_sync_restarts_amuled_on_the_forwarded_port_only_when_it_moved`
    passed; in CI, run 39614336152 on amd64 and arm64. Seen failing twice in throwaway builds: `with_listen_port`
    not updating the section fails it on `amule.conf's ports: expected '40123 40123', last was '4662 4672'`;
    `is_amuled_restart_due` restarting on equal ports fails the negative side on `assert '4662 4662' == '4662 4672'`.

## Holistic review

`.reviews/lot3b-holistic.md`: 0 critical, 0 major, 10 minor. Every finding exits fixed in the lot.

1. **`amule.conf`'s 0600 only as good as a leftover temporary file; a failed write leaves it behind**: fixed in
   block 60. `PosixAmuleConf` unlinks `amule.conf.tmp`, creates it with `O_EXCL` at 0600, and removes it when the
   write, the chown or the replace raises. Two tests, each seen failing first: a stale 0644 `amule.conf.tmp`
   (`assert 420 == 384`), and a chown that raises (`amule.conf.tmp` still listed beside `amule.conf`).
2. **No unit test pins the boot's order**: fixed in block 60. The boot's fakes record into one action list and
   `test_each_step_runs_as_puid_and_pgid_in_order_port_sync_last` asserts the sequence; `PosixAccountManager` is
   tested with the group present and the user missing, through two separate lookups. The review's mutations (a)
   `set_admin_password` before the directories, (b) the `down` file before the account, (e) `groupadd` guarded by
   the user lookup now each fail a test (`At index 1 diff: 'admin password s3cret as 1000:1001' != 'directories
   1000:1001'`; `At index 0 diff: 'disable port-sync' != 'account 1000:1001'`; `groupadd` listed before
   `useradd`). Mutations (c) and (d), in `__main__`'s paths, stay the compose smoke's, as on `main`.
3. **Two shapes for the hexagon's driving ports**: fixed in block 60, the lead's choice by precedent.
   `RunPortSyncLoop` drops `PortSyncLoopRunner`, as `RunCrawler` has no port; `PortSyncApp` alone implements it,
   holding `env` from its constructor as `CrawlerApp` does; the boot keeps `boot_container(env)` per call.
   `AGENTS.md` names both roots; the spec carries a `(Corrected: ...)` in its hexagon table and at row 57.
4. **Four spec claims changed with no `(Corrected: ...)`**: fixed in block 60: the header lists the narrowed
   behaviours, the temporary file's rename and the boot's switch to `os.replace`; the hexagon table's port-sync
   row (finding 3); the `Logger` row (finding 7); the 3b 40 fallback.
5. **C1 and C2 still exempt `p2pwatch_amule`**: fixed in block 60: "`vex_checks` and `coverage_checks` follow it
   from lot 3c"; 3c's Wrap drops the clause.
6. **`MonotonicInstant` carries what no production path uses**: fixed in block 60. It keeps `__sub__` between two
   instants and the `datetime` refusal (now a `NotImplemented`, seen failing on `AttributeError` without it);
   `__add__`, the `timedelta` subtraction and `order=True` went with their tests, `FakeMonotonicClock` builds its
   instants itself. The spec's `MonotonicClock` row says so.
7. **One value under several names, one logger name that names nothing**: fixed in block 60. `forwarded_port`
   throughout the round; `listen_port` in the round and in `is_amuled_restart_due`. The boot's
   `S6ServiceSupervisor` keeps its logger: the class logs a failed `s6-svc` on amuled's stop and start, which only
   port-sync calls, so sparing the boot's instance a logger would take splitting `ServiceSupervisor`. The spec's
   `Logger` row says the third name is the boot's and never written.
8. **Leftovers of the move, one double under three names**: fixed in block 60: `Node.run_loop`, `node.actions`
   (now also holding the conf's reads and writes), "asks the supervisor nothing" in the three names; one
   `FakeOwnership` and one `FakeCommandRunner` in `tests/fakes.py`, which replace `FakeS6`, both `FakeSystem`s,
   `_Ownership` and the two `FakeOwnership`s. Two port-sync tests the sequence now covers went
   (`test_the_file_is_written_only_once_amuled_is_down`, `test_the_written_file_is_owned_by_puid_and_pgid`).
9. **Pull request bodies naming blocks 56 or 58 for block 57's work**: fixed by the lead, who edited #349, #350 and
   #351.
10. **`build_opener()`'s comment explains by code no longer in the tree**: fixed in block 60. Port-sync keeps
    following the environment's proxies to reach gluetun, no operator-visible change; the comment says that.

## Departures from the spec

- **Split**: block 56 (893 lines, 17 files) into 56 and 57, along the seam blocks 50 to 54 used. No size
  exemption.
- Block 40: `boot.main` parsed the settings a second time until block 48 deleted it.
- Block 42: `AmuledDirectoryPreparer` for the spec's `MountPointPreparer` (the operator's rename).
- Block 48: `architecture.md` section 12's boot path moved here from block 58; block 57 took port-sync's.
- Block 50: `PortSyncSettings` kept integers until block 52 turned them into `timedelta`s.
- Block 54: two class 2 answers from the lead (the URL at the reader's constructor; `run_port_sync` a callable
  passed to `main`), an interim seam blocks 57 and 58 replaced by `PortSyncApp`; gluetun's timeout a composition
  value (10 s).
- Block 56: port-sync's `amule.conf` owner is `PUID:PGID` from its settings (the lead's reading of block 44's
  report); a missing `amule.conf` logs `amule.conf does not exist` instead of `open`'s errno text, the format
  string unchanged.
- Block 58: the monotonic clock a parameter of `PortSyncApp`, so the wiring test stops the loop; boot's
  `S6ServiceSupervisor` logs under `p2pwatch_amule.application.boot_container` (it logs nothing today).
- Block 59: `test_port_sync_stays_down_then_its_rights_let_amule_restart_amuled` became
  `test_port_sync_stays_down_with_port_sync_unset`: its manual `s6-svc -wD -d` and `-u` as `amule` went, since the
  new case has port-sync itself do both through the same rights. The smoke stack gained `PORT_SYNC_POLL_SECONDS`.
- Block 60: `RunPortSyncLoop` behind no port (holistic finding 3), recorded in the spec.

## Names settled by teammates

By rule or precedent, each in its block's report: `boot_container`, `find_or_create_amule_account`,
`prepare_amuled_directories`, `read_amule_conf`/`write_amule_conf(conf, uid, gid)`, `set_admin_password`,
`enable_port_sync`/`disable_port_sync`, `stop_amuled`/`start_amuled`, `is_amuled_restart_due`, `poll_interval`,
`restart_min_interval`, `read_forwarded_port`, `run_port_sync_loop`, `PortSyncApp`; the callables `run_command`,
`change_owner`, `find_group`, `find_user`; the fakes in `packages/amule/tests/fakes.py`. Block 59:
`_GLUETUN_STAND_IN_ROOT`, `_GLUETUN_STAND_IN_LOG` and `_serve_forwarded_port` after the spec's word "stand-in"
and `FakeGluetunControlServer`'s "gluetun"; `_listen_ports` after `tcp_listen_port`; `_amuled_up_and_pid` after
the `s6-svstat` fields it reads. Block 60: `forwarded_port`, `listen_port`; `FakeCommandRunner` (it replaces
`run_command`), `FakeOwnership`.

## Pitfalls

- **Serena's rename from a port reached the port alone** in `p2pwatch_amule` (block 42): its language server did
  not index the package's new `ports/` modules. Rename by hand, then `git grep -w` the old name.
- **A fake recording into its own list cannot pin an order across ports** (block 60): the boot's order was
  untested for the whole lot. Fakes whose order matters share one action list.
- **`os.open(..., O_CREAT, 0o600)` sets the mode only on creation** (block 60): an existing file keeps its own,
  and `os.replace` carries it over. Unlink first, then `O_EXCL`.
- **`http.server` strips a leading `//` from `self.path`** (block 54): a loopback stand-in that records `path`
  cannot see a doubled slash; record `requestline`. `serve_forever`'s 0.5 s poll slows each teardown; poll faster.
- **In zsh, `$vars` is not word-split** (block 48): an `env -i $vars` loop passes one variable; use bash.
- **amuled writes `Port=4662` and `UDPPort=4672`** at its first start (block 59): port-sync compares the TCP port
  only, so a forwarded 4662 leaves `UDPPort` at 4672. A real tunnel forwards another port.
- **The native engine had no `veth`** (block 59): the kernel was updated without a reboot, so
  `DOCKER_CONTEXT=default` failed with `operation not supported`, as `docs/contributing/testing.md` says; the run
  went to Docker Desktop.
- **Host port 4711 is the deployed node's**: never publish it, never touch the `mulewatch-*` containers.

## Not validated

- `compose_integration` locally on a native engine: on Docker Desktop, block 59 had 8 passed and the known
  completion failure (`expected 'completed True', last was 'downloading False'`). CI's `build-and-verify` is
  authoritative on amd64 and arm64.
- The api, download and orchestration suites were not run locally in this lot.
- Port-sync against a real gluetun: the smoke's stand-in serves a static file; the deployed node never ran the
  stack.
- Block 60's `PosixAmuleConf` change under the real boot as root: the unit tests run on `tmp_path`; block 60's CI
  run is the first compose smoke over it.

## Wrap counts

From `gh run list --branch <branch>` over blocks 40 to 59 on 2026-10-21, before block 60's own run.

- **Runs**: 19 for 12 blocks. Each block's current head has one green run. The 7 others: #345 `90e15e2b` green,
  then `5944d482` (the operator's rename, a fix-back); #347 `b4489d32` green, then `b607d827` twice (one
  cancelled), cascaded onto block 42's rename; #349 `d7d85ca3` green, then `53531025` (the lead's docs fix-back);
  #350 `2b793ef9` cancelled, then `b29971eb` twice (one cancelled), cascaded onto block 48's fix-back; #354
  `0cbfbc1e` cancelled, then `e1fb2cf3` (the lead's docs fix-back).
- **Fix-backs**: 3 (blocks 42, 48, 57). **Cascaded rebases**: 2 (block 44 onto 42, block 50 onto 48). **Runs they
  re-triggered**: 7, fewer than the 12 blocks.
- **Splits**: 1 (56). **Exemptions**: none.
- **Bodies called unreadable**: none at writing; the operator has not reviewed the stack yet. The lead corrected
  three bodies (#349, #350, #351) after the holistic review.

## Next

- The operator reviews and merges the stack, after the lead rebases it onto `main` if `main` moved.
- "A copy before a migration that rewrites rows" ships before any release; this lot changes the aMule image.
- **Lot 3c**, `vex_checks`, `coverage_checks`, `template_checks` and the no-module-patching rule, from the tree 3b
  leaves, re-measuring its blocks first. Then "Contract tests for the fakes", which waits for every port's final
  shape.
