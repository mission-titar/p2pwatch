# Handoff: the five other hexagons, lot 3a of the hexagonal architecture umbrella

Drafted by block 32 from the lot's block reports (#331, #332, #334 to #342), for the closing block 90 to correct
with the holistic review and the operator's answers.

## State

Tier Spec lot. Spec `agents/specs/2026-10-20-five-hexagons.md`, approved by the operator on 2026-10-20 (reviewed in
`.reviews/lot3-spec.md`, gitignored: 0 critical, 12 major, 19 minor, each answered in the spec). It carries out lot
3 of the umbrella spec `agents/specs/2026-10-18-hexagonal-architecture.md`. The spec first planned two lots (3a, 3b);
the operator cut it into three on 2026-10-21, once 3a's splits had used its cap (`a3120abc`): 3a, the crawler's
leftovers, `amule_bump` and `p2pwatch_amule`'s settings; 3b, the aMule container's boot and port-sync (the former
3a blocks 40 to 56); 3c, the three checking tools, the rule and the documentation.

One stack cut from `main` at `38bfe15` (gh stack #333). The spec's 3a rows 10 to 30 became 11 blocks by splits
(blocks 20, 21 and 30 split; 14 and 16 were added after the operator's approval), plus the closing block.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #331 | `test/crawler-constants-as-parameters` |
| 11 | #332 | `test/crawler-connections-closed` |
| 12 | #334 | `test/crawler-process-state-as-values` |
| 14 | #335 | `refactor/adapter-values-from-composition` |
| 16 | #336 | `refactor/config-defaults-in-domain` |
| 20 | #337 | `refactor/bump-amule` |
| 21 | #338 | `feat/bump-amule-use-case` |
| 22 | #339 | `feat/bump-amule-driving-port` |
| 24 | #340 | `refactor/repo-reader-domain-types` |
| 30 | #341 | `refactor/amule-settings-in-domain` |
| 32 | #342 | `refactor/amule-paths-from-main` |
| 90 | closing | `docs/five-hexagons-3a-wrap` |

Nothing of the stack is merged. The lot changes what both images run (the crawler's amuleapi transport, the aMule
container's Python), so a release is possible after the merge, but not before the backlog's "A copy before a
migration that rewrites rows" ships (spec, section "Backlog").

## What was built

- **Constants as parameters, the runner and the memo apart** (block 10): `reevaluate_catalog` takes its progress
  cadence, which the composition passes (200 files). The migration runner receives its scripts, so
  `open_catalog(path)` and `open_local(path)` keep applying their own and a test hands it a probe migration. The
  memo is a generic `create_memoized_function`; `register_sql_functions` keeps `content_hash` and `fold_raw_meta`.
  `open_catalog_forcing_secure_delete_at` replaces the migration tests' patch of the image's `SECURE_DELETE`.
- **No unclosed connection** (block 11): the crawler's pytest config turns `ResourceWarning` and
  `pytest.PytestUnraisableExceptionWarning` into errors; the readers' tests open `with ReaderProvider(...)`, seeding
  goes through `with closing(sqlite3.connect(db)) as conn, conn:`; `close_test_connections` is deleted. The
  shutdown-deadline wiring test asserts its one deliberate leak (`pytest.warns(ResourceWarning)`).
- **Process state from `__main__`** (block 12): the crawler's `main(argv, env, cwd)`, no `argv=None`; the root
  logger handed to the command line (format, INFO, left alone once it has a handler) and to `CrawlerApp` (the
  config's level); every path argument, defaults included, taken under `cwd`; `start_http_server` a parameter of
  `start_metrics_server`; `PathlibCatalogFinder` renamed `FilesystemCatalogFinder`, which now only sees absolute
  paths. C2 and C3 in `AGENTS.md`.
- **The values an adapter drives from the composition** (block 14): the six parameter defaults only tests changed
  are gone. `AmuleApiClient` takes a `transport_factory` (one transport per session, as before) and its timeout;
  `AppriseNotifier` its `apprise_factory`; `RandomJitterGenerator` its seed (`None`, the system's entropy);
  `UvicornServerThread` its start timeout and serving resources.
- **`crawler.yml`'s absent keys take the domain's values** (block 16): the twelve values in
  `p2pwatch.domain.config_defaults`, with their reasons; the config dataclasses lose every field default; an absent
  section parses as an empty one. C5 in `AGENTS.md`.
- **`amule_bump` on ports** (blocks 20 to 24): the driven ports `DockerfileReader`/`DockerfileWriter`
  (`FilesystemDockerfile`), `PullRequestBodyWriter` (`FilesystemPullRequestBodyWriter`), `StepOutputWriter`
  (`GitHubStepOutputWriter` given `GITHUB_OUTPUT`'s path, `TerminalStepOutputWriter` outside Actions);
  `main(argv, env, cwd, temporary_directory, github_api_url)`; `BumpAmule` behind `AmuleBumper` returns
  `AmuleBump(new_pin, body)`, `PinIsLatest(version)` or `PinAheadOfLatest(pinned_version, latest_version)`, which the
  command line prints; `bump.py` is deleted. `RepoReader`'s four `read_` methods return domain types
  (`GitObject(kind, object_id)`, `GitObjectKind` a `StrEnum`); GitHub's API URL is a value of `__main__`; the
  adapter's and the wiring tests run against `FakeGitHubServer` on a loopback port. `amule_bump` has no
  `monkeypatch` and no deprecated edge left.
- **`p2pwatch_amule`'s settings in the domain** (blocks 30, 32): `p2pwatch_amule.domain.settings` parses the
  boot step's variables (`BootSettings`, `parse_boot_settings`) and port-sync's (`PortSyncSettings`,
  `is_port_sync_enabled`, `parse_port_sync_settings`, the three `DEFAULT_*`), raising `SettingsError`
  (`domain/settings_error.py`) with the messages of before. `ArgparseCommandLine.run(argv) -> int` prints the
  error and returns 1; `__main__.main(argv, env) -> int` passes the environment, the root logger and the
  container's paths (`_HOME_DIR`, `_CONFIG_DIR`, `_AMULE_CONF_PATH`, `_PORT_SYNC_DOWN_FILE`,
  `_AMULED_SERVICE_DIR`; the mount points from `domain/conf.py`'s `INCOMING_DIR` and `TEMP_DIR`, which
  `reconcile_conf` writes) to `boot.main` and `port_sync.main`. `adapters/driven/settings.py` and its two
  deprecated edges are gone.

## What an operator sees change

- **amuleapi no longer follows `HTTP_PROXY`/`NO_PROXY`** (block 14): httpx reads them only when it builds its own
  transport. `deploy/` sets none and amuleapi is reached inside the compose network. `docs/` mentions neither
  variable, before or after.
- **A merge error or log line names the absolute path** of a relative argument (block 12).
- **A manual `amule_bump` run that is not a dry run prints `version=` and `body-path=`** (block 21),
  `TerminalStepOutputWriter`'s lines; `docs/contributing/amule-bump.md` says so.
- The aMule container: nothing. The same variables, values when unset, refusal messages and exit code (blocks 30,
  32, below).

## Acceptance

3a meets 8, 11, 9 and 10, and 1, 3 and 4 for the crawler and `amule_bump` (spec, Acceptance, corrected by
`a3120abc`). Re-run by block 32 at `a3120abc` on 2026-10-21 unless noted.

1. `git grep -nE "monkeypatch|MonkeyPatch|mock\.patch|from unittest\.mock import.*patch" -- '*.py'` prints 0 lines
   under `packages/crawler`, `packages/crawler_testing`, `packages/matching` and `packages/amule_bump`; 57 lines in
   11 files remain, all in `amule` (28), `vex_checks` (23) and `coverage_checks` (6), for 3b and 3c (133 lines in 27
   files on `main`).
3. `grep -c "deprecated = true" tach.toml` prints 15 (19 on `main`), none on a crawler or `amule_bump` module; a
   `tomllib` pass over `tach.toml` finds no plain edge from an `adapters` module to another.
4. `grep -rn "^def main" packages/*/src` lists the crawler's and `amule_bump`'s `__main__.py` only, for those two
   packages; 9 others remain (`boot`, `port_sync`, the four VEX checks, `check_templates`, `read_names`,
   `unit_coverage`).
8. Block 24: a loopback server replaying 8 recorded GitHub answers (3.0.1 to 3.1.0); `main`'s code from a
   `git archive` with the URL edited, and the branch's with the URL passed, print the same 767 lines, 49,888 bytes
   (sha256 `62b78935...343d`): the same pin and the same 49,539-character body.
9. `git diff --stat main...HEAD` over `deploy`, `security`, the crawler's `migrations`, `packages/amule/docker`,
   `packages/amule/Dockerfile` and `.github/workflows` prints nothing; the 8 environment variable names under
   `packages/amule/src` are the same on `main` and at the top.
10. The gate green at every block (each report), and CI green at each block's current head (Wrap counts).
11. Block 11: an injected test that leaves `sqlite3.connect(tmp_path / "leak.db")` open makes the crawler suite exit 1
    (`1 failed, 1465 passed`, `ResourceWarning: unclosed database`); with `-W error::ResourceWarning` alone it passes,
    hence the second filter.

Checked ahead of 3b, which owns Acceptance 6: the boot step's and port-sync's 6 refusal messages are the same
strings on the parent of block 30 and at block 32's top, and `python -m p2pwatch_amule` under `env -i` prints the
same stderr line with exit 1 on both sides, for `boot` with no variable, `boot` with `PORT_SYNC=maybe` and
`port-sync` with `PORT_SYNC_POLL_SECONDS=0` (blocks 30, 32).

## Departures from the spec

- **Splits**: block 20 (23 files, into 20 and 21), 21 (547 lines, into 21 and 22, the repo reader renumbered 24), 30
  (823 lines, into 30 and 32). Blocks 14 and 16 were added after the approval. No size exemption.
- Block 10: the runner "moves apart" within `connection.py` (`_open`, `_load_scripts`, `_apply_migrations` already
  took their input; a module of its own would cost twice its size); the close-on-error test fails through a
  `PersistenceError`, the close being unconditional.
- Block 11: the second filter, `error::pytest.PytestUnraisableExceptionWarning`; the deadline test rewritten to
  assert its leak. D1b's "visible where it happens" holds partly: the failure lands on the test running when the
  garbage collector runs, since a per-test `gc.collect()` took the suite from about 19 s to 47 s.
- Block 12: `start_http_server` typed `Callable[..., tuple[BaseServer, Thread]]` (a keyword after `addr` needs a
  `Protocol`, which the crawler's `src` refuses); every path argument under `cwd` (the lead's request), so the
  finder lost its `cwd` again and C2's example became `AmuleApiClient(host, port, ...)`.
- Block 14: a `transport_factory`, not a transport (the operator's answer).
- Block 16: no `tests/domain/test_config_defaults.py`: what an import runs counts as covered, and the parser's tests
  pin the twelve values; the parser's private `_seconds(default=...)`, `at_most` and its bounds stay.
- Block 22: the command line still catches `OSError` beside `BumpError`, the driven ports documenting it.
- Block 24: `GitObjectKind` reached through an explicit `_KINDS_BY_GITHUB_TYPE` dict, so vulture sees its members;
  an unknown type is a `KeyError`.
- Blocks 30, 32: the boot step's own variables moved too (`BootSettings`), so that no adapter exits; `SettingsError`
  in a module of its own (the lead's amendment); the port-sync test drives a stand-in s6 directory,
  `/run/service/amuled`, to show the path is the one passed.

## Spec corrections

Each a `(Corrected: ...)` in the lot's spec: C1 (no parameter default; an adapter's own code is no parameter, the
runner and the memo apart, block 10); C5 and the six parameter defaults (blocks 14 and 16 added); D1's
`argv=None` fixed by the block that touches each command line; `amule_bump`'s three outcomes (block 22); the block
table's splits (20, 21, 22, 24; 30, 32); the cut into 3a, 3b and 3c, with the Acceptance each meets (`a3120abc`).
Block 11's report corrects a measurement the spec carries: of the 5 files using `close_test_connections`, 2 still
opened connections.

## Tests pruned or moved

- Block 10: `test_progress_cadence_is_every_200_files`, which pinned the module constant now passed by the
  composition.
- Block 11: the fixture `close_test_connections` and three `usefixtures` marks that did nothing.
- Block 12: `test_crawler_loop.py`'s `caplog.at_level`, there only to restore the root level.
- Block 22: `test_bump.py`, with `bump.py`, its cases on `test_bump_amule.py` and the command line's tests.
- Blocks 30, 32: the boot step's and port-sync's refusal tests moved to `tests/domain/test_settings.py`, every case
  kept; `test_boot.py` keeps one parametrized test that a refused variable, boot's or port-sync's, stops the boot
  before any command, chown or directory.

## Class 1 fixes

- Block 16: a test comment saying the parsed webui "carries only `enabled`".
- Block 24: vulture's report on `GitObjectKind.TREE` and `BLOB` (above).

## Operator decisions

Taken during Act, each from a class 2 question or a point the lead brought:

- Block 10: the first version gave `open_catalog` and `register_sql_functions` parameters with defaults; the
  operator refused the defaults (the composition passes the real value), then settled that an adapter's own code is
  no parameter (spec commits `d188bae`, `58cdab7`).
- After the approval: C5 and blocks 14 and 16, from the default-values sweep (`.reviews/lot3-default-sweep.md`).
- Block 14: the transport's shape, a factory ("Reco ok").
- Block 21: `TerminalStepOutputWriter` outside Actions (option (a)); the names `changelog_width_characters`,
  `temporary_directory`, `AmuleBumper.bump_amule`, `BumpAmule`.
- Block 22: the three outcomes, `AmuleBump`, `PinIsLatest`, `PinAheadOfLatest`.
- Block 24: the four `read_` methods, `GitObject(kind, object_id)` (`object_id` the lead's amendment for `sha`),
  `GitObjectKind`, `GitHubRepoReader(api_url, full_name, token)`.
- Block 30, through the lead: the names, the boot step's variables in the block, `SettingsError` in its own module;
  then the split into 30 and 32. From then on a teammate settles a name that a rule or a precedent decides, and
  notes it in its report.
- The cut of lot 3 into 3a, 3b and 3c, once 3a's splits had used the cap.

## Pitfalls

- **Host port 4711 is the deployed node's** (gluetun publishes amuleapi there): the integration suites' documented
  `-p 4711:4711` cannot start the throwaway daemon, and the suites then talk to the real node with the test
  password (block 14: 5 failed on refused logins, nothing changed on the node). Publish it as
  `-p 127.0.0.1:14711:4711` with `P2PWATCH_TEST_API_PORT=14711`; never touch the `mulewatch-*` containers.
- **A rename git no longer pairs counts twice**: below 50 % similarity a moved file is a deletion and an addition
  (block 30: 823 lines, 389 of them `settings.py` and its test; 571 with `-M30%`). Keep a moved module's content and
  its tests' names close when the bound is near, as lot 2 found.
- **A scope added in Act is not in the estimate**: block 30's estimate (300) left out the boot step's variables,
  which its brief's "the environment's validation" covered.
- **`error::ResourceWarning` alone does not fail on a leak**: a finalizer's warning goes to
  `sys.unraisablehook`, which pytest reports as `PytestUnraisableExceptionWarning` (block 11).
- **`closing(sqlite3.connect(...))` does not commit**: `close()` rolls back, so seeding keeps the inner `conn`
  context manager (block 11).
- **Serena's `replace_symbol_body` on a decorated test replaces its decorators too** (block 11).
- **A multi-occurrence regex over signatures also hits those wrapped for length** (block 10); ruff's E501 caught
  two.
- **Branch coverage does not see a conditional expression** (block 20): `__main__`'s `GITHUB_OUTPUT` mapping was
  half untested until `env` became a value.
- **vulture cannot see enum members built by value** (block 24): map through an explicit dict rather than
  whitelist them.
- **A stale `.pyc` runs old bytecode**: clear every `__pycache__` before a gate run (every block did).
- Port 8765 was taken on the machine (block 24); the replay server used 18765.

## Not validated

- `compose_integration` locally: its completion test fails under Docker Desktop by design. CI's
  `build-and-verify` ran it on amd64 and arm64 at every block's head, the boot step included at blocks 30 and 32.
- Locally, the api, download and orchestration suites passed (6 tests) against `p2pwatch-amule:main` on port 14711
  at block 14 only; block 12 ran `test_crawler_loop.py` and the compose harness's two tests.
- `amule_bump` against the real `api.github.com` from the branch: the weekly workflow is the first run. urllib
  still reads `HTTP_PROXY` for GitHub, unchanged and wanted.
- Port-sync's path that stops amuled, rewrites the ports and starts it again: tested nowhere, 3b's block 56 adds it.
- The deployed node never ran the stack.
- **No new test watched failing** in blocks 14 and 16, which add no behaviour: block 14's check is `mypy --strict`
  on a scratch file omitting each value (six `call-arg` errors); block 16 mutated each of the twelve values in turn,
  each failing a parser test.

## Holistic review

Not run yet: `lot3a-holistic` over `git diff origin/main...origin/refactor/amule-paths-from-main`. Block 90 writes
its counts and each finding's exit here.

## Wrap counts

Draft from `gh run list --branch <branch>` on 2026-10-21, before the closing block; block 90 recounts.

- **Runs**: 15 over the 11 blocks. Each pull request has one green run at its current head, with `build-and-verify`
  on amd64 and arm64, but #342, whose run at `a3120abc` (the lead's spec cut) is in progress after a green one at
  `f0393436`. The others:
  - #331 at `0d0544e1`, green, superseded by the fix-back below;
  - #332 at `451a2139`, green, superseded by the cascade below;
  - #334 at `e94a5cf0`, cancelled by the push of `81ca9aa4` (every path argument under `cwd`, the lead's request).
- **Fix-backs**: 1, block 10 (`0d0544e1` to `33d95253`, the operator's refusal of the defaults).
- **Cascaded rebases**: 1, block 11 onto block 10's fix (`451a2139` became `0fd29189`), one run re-triggered.
- **Splits**: 3 (20, 21, 30) and 2 blocks added (14, 16). **Exemptions**: none.
- **Bodies called unreadable**: none at writing; the operator has not reviewed the stack yet.

## Next

- Block 90 (`docs/five-hexagons-3a-wrap`): the holistic review's findings; `BACKLOG.md`'s lot 3 sub-item narrowed to
  3b and 3c; this handoff corrected.
- The operator reviews and merges the stack, after the lead rebases it onto `main` if `main` moved.
- "A copy before a migration that rewrites rows" ships before any release; this lot changes both images.
- **Lot 3b**, the aMule container's boot and port-sync, from the tree 3a leaves, re-measuring its blocks (40 to 56,
  closing 60) first. It starts from `boot.main(env, *, <paths>)` and `port_sync.main(env, *, <paths>)`, which take
  every value from `__main__`; what its tests still patch is `subprocess.run`, `grp`, `pwd`, `os.chown`,
  `os.replace`, `time`, `forwarded_port` and `urllib.request.urlopen` (`test_gluetun.py`), and port-sync's edge to
  `gluetun` is its last deprecated one. The command line's `sync_listen_port` becomes `port_sync_loop_runner` at
  block 54 (D4).
- Then lot 3c, the checking tools and the rule, and "Contract tests for the fakes", which waits for every port's
  final shape.
