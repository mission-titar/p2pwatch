# Handoff: monotonic clock, and persistence without a clock

Drafted by block 90 from the lot's block reports (#217 to #226), corrected by the closing block 100.

## State

Tier Spec lot, operator surfaces included (`local.db`'s schema, the webui's `/node`), spec
`agents/specs/2026-10-14-monotonic-clock.md` (approved 2026-10-14 after the spec review
`.reviews/monotonic-clock-spec.md`: 1 critical, 3 major, 13 minor, all answered). Ten blocks, one stack cut
from `main` at `10b45f0`: #217 (10, `refactor/catalog-without-clock`), #218 (20,
`refactor/downloads-without-clock`), #220 (30, `refactor/monotonic-clock-client`), #221 (40,
`refactor/monotonic-intervals`), #222 (50, `refactor/wall-clock-port`), #223 (60, `refactor/loss-detection`),
#224 (70, `refactor/backoff-key`), #225 (80, `refactor/backoff-states-table`), #226 (90,
`refactor/console-clock-lint`), then the closing block 100 (`docs/monotonic-clock-wrap`), which holds the
holistic review's fixes, `BACKLOG.md` (D12), the spec's corrections, D11's correction of the 2026-10-13 spec
and this handoff.

Nothing of the stack is merged. `git tag -l 'v*'` still ends at `v4.1.0`. `local.db` goes to schema
version 11 (`local/0011_backoff_states_table.sql`); the catalog stays at 12, no catalog migration in the lot
(acceptance 8).

Once merged, no repository holds a clock, every interval and deadline kept in memory runs on a
`MonotonicClock`, every stamp on a `WallClock`, the two waits that survive a restart (the search backoff,
the lost-download detection) store their start and their duration, and ruff's `TID251` refuses a system
clock read outside the two clock adapters.

## What was built

- **The catalog without a clock** (block 10): `record_observation(observation, observed_at)`,
  `record_decision(file, decision, decided_at)`, `record_retraction(file, target_id, decided_at)`; the
  use-cases read the clock right before each write; `WorkerDeps` and `reevaluate_catalog` carry it; the two
  `catalog_matching` texts say the crawler adds `decided_at`.
- **Downloads and the node identity without a clock** (block 20): `record_queued(..., queued_at)`,
  `record_completed(file, completed_at)`, `set_state` typed `Literal[DOWNLOADING, FAILED]`,
  `mark_seen(statuses, seen_at)`, `get_or_create_node_id(created_at)`; `expire_lost(unseen_since)` as a
  transient state; `utc_iso`'s message in English (D11).
- **The monotonic clock and the amuleapi client** (block 30): `MonotonicClock`, `MonotonicInstant` (integer
  nanoseconds, its arithmetic and ordering refusing a `datetime` for mypy and at run time),
  `AsyncioMonotonicClock`, the tests' `FakeTime` (`advance`, `step_wall`, `sleeps`, views `wall` and
  `monotonic`); the client paces its starts and bounds its searches on the monotonic clock alone, "no start
  yet" is `None`; the compose smoke's script follows (D11).
- **The other intervals** (block 40): the sources gate, `StatusBoard.is_current(client_name)` on the
  instant of each publication, `_AlertTimer`, every loop's `sleep`; `Clock.sleep` leaves the port.
- **The wall clock port** (block 50): `WallClock`, `SystemWallClock`, `Rng` and `SeededRng` in modules of
  their own; `Clock`, `AsyncioClock`, the last `FakeClock` and `LoopClock` gone; every `clock` is
  `wall_clock` beside `monotonic_clock`.
- **Loss** (block 60): `domain/persisted_wait.py`'s `remaining_wait`; `DownloadDeps.loss_deadline_by_file`,
  reconciled each cycle with `last_seen_at_by_file()` (which reads `COALESCE(last_seen_at, queued_at)`);
  `expire_lost` and `_EXPIRE_LOST` gone; `DownloadDeps.lost_after` a `timedelta`.
- **`BackoffKey`** (block 70): `BackoffKey(client_name, channel)` replaces the string keys, the JSON row
  still encoding them.
- **`backoff_states`** (block 80): `local/0011` creates the `STRICT` table and drops `scheduler_state`;
  `BackoffState(attempts, started_at, delay)`, `BackoffStateRepository`; `BackoffRegistry` takes both
  clocks and loads each wait through `remaining_wait`; `/node`'s "Backoff" section.
- **The console's clock and the lint** (block 90): `run_query` measures its budget and its elapsed time on
  the `MonotonicClock` `build_app` passes it; `TID251` bans the 13 calls of D10, each message naming the
  port; `search_tasks.py`'s yield keeps a `# noqa: TID251`; `AGENTS.md` gains the invariant "persistence has
  no clock" and the hard rule "only the clock adapters read the system clock".
- **Wrap** (block 100): a composition test pins the backoff's reload at boot; the status loop's four
  durations are `timedelta`s; `BackoffRegistry.time_until_retry`, `save_backoff_states(backoff_state_by_key)`
  and `BackoffEntry.retry_at_display`; the spec's corrections, section 8 of the 2026-10-13 spec,
  `AGENTS.md`'s `TID251` rule, `local.db`'s tables in `docs/contributing/architecture.md`, `BACKLOG.md`.

## Decisions taken during Act

No block report records a class 2 question. The operator answered two points mid-lot, both "A", and the
lead chose two of the holistic review's fixes for block 100 (Holistic review below):

- Block 20's `expire_lost(unseen_since)`, the loop computing the cut-off on the wall clock until block 60
  deleted it, so that the repository lost its clock in block 20; block 60 adds the transient state to the
  spec with its `(Corrected: ...)`.
- Block 60's `NULL` `last_seen_at`: `last_seen_at_by_file()` reads `COALESCE(last_seen_at, queued_at)`, as
  local 0005's backfill does, so such a row waits from its queuing instead of stopping the download loop
  (the lot's one fix-back, `0011b1c`).
- Block 100, the lead: the status loop's four durations as `timedelta`s, one convention per module, rather
  than `STATUS_PERIOD` back to float seconds; and `StatusBoard.is_current`'s `False` for a client not read
  yet kept as the board's contract for an unknown client, its red quoted below.

Each block's other departures, the ones a reviewer may weigh:

- Block 10: the use-cases take the clock as `clock` until block 50.
- Block 30: `LoopClock` keeps `Clock` and gains a monotonic view (`LoopMonotonicClock`, `MONOTONIC_EPOCH`);
  `_POLL_INTERVAL` a `timedelta`; the difference of two instants rounds to the microsecond, half to even;
  `FakeAmuleApi` lives on the monotonic view; the step test covers Kad too.
- Block 40: `Clock.sleep` leaves the port, `AsyncioClock` and `LoopClock` (its last caller moved);
  `test_run_download_cycle.py`'s `FakeClock` goes here; `STATUS_PERIOD` and `READING_FRESH_FOR` are
  `timedelta`s (block 100 made the two alert delays follow), `poll_interval_seconds` stays a float
  converted at its sleep; the board writes the instant before the reading, and a client not read yet is not
  current.
- Block 50: `LoopClock` deleted rather than given two views (D4): `LoopWallClock` and `LoopMonotonicClock`
  both read the loop's time; one `TickingWallClock` in `fakes.py`; two `clock.sleeps == []` assertions
  deleted, the type guaranteeing them.
- Block 60: a deadline has passed at `monotonic_now >= deadline`, where `_EXPIRE_LOST` compared strictly;
  the loss step reads the wall clock only for a download it meets without a deadline; a failed download
  leaves the map at once.
- Block 70: `BackoffKey` lives in the repository port; `channel` has no default; the JSON row keeps its
  `client` or `client:channel` format.
- Block 80: `/node` prints the planned retry as the stored ISO-8601 UTC with microseconds, not the other
  pages' `YYYY-MM-DD HH:MM:SSZ`; `time_until_ready` and `BackoffRegistry.remaining_wait` (block 100 renamed
  it `time_until_retry`) return a `timedelta`; the runner's repository parameter is `backoff_states`; the
  migration file is `0011_backoff_states_table.sql`; `started_at` is written through
  `iso_to_micros(utc_iso(...))`; the webui reads `BackoffRow` and formats `BackoffEntry`.
- Block 90: `run_query` keeps `timeout_seconds: float` and converts it once into a `timedelta` budget, since
  `TIMEOUT_SECONDS` is public and its error message counts seconds; `build_app` takes `monotonic_clock`; the
  noqa's reason sits on the line above the call, which cannot hold both under 100 columns;
  `time.clock_gettime` and `clock_gettime_ns` name both ports in their message.

## Class 1 fixes

- Block 10: the catalog port's docstring said its stubs fit on one line; the composition test renamed
  `test_the_rows_written_carry_the_apps_clock`.
- Block 20: D11's `utc_iso` message and docstring; the `DownloadRepository` docstring listed six of eight
  methods; a test comment named `set_state(COMPLETED)`; `_MARK_SEEN`'s `:now` became `:seen_at`.
- Block 60: `test_record_queued_stamps_last_seen_at_with_queued_at`'s comment.
- Block 80: `AmuleEndpoint`'s docstring named `scheduler_state`; the adapter tests' names said
  `channel_backoff`.
- Blocks 30, 40, 50, 70, 90 and 100: none.

## Spec corrections

Every `(Corrected: ...)` in `agents/specs/2026-10-14-monotonic-clock.md`, and the block that added it:

- Section 2, asyncio's timeouts: `TID251` can see `asyncio.wait_for` and `asyncio.timeout` and leaves them
  allowed by choice; only `loop.time()` is out of its reach (block 100, the holistic review).
- D2: `STATUS_PERIOD` is a `timedelta` passed to `sleep` as is; only `poll_interval_seconds` converts
  (block 100, the holistic review).
- D4: `LoopClock` deleted for `LoopWallClock` and `LoopMonotonicClock` (block 100, the draft).
- D4: `_BlockingClock` and `_StubClock` became `_BlockingMonotonicClock` and `_StubWallClock`; blocks 10 and
  20 deleted `_AdvancingClock`'s four copies (block 100, the holistic review).
- D10: the yield is now `search_tasks.py:61`, its reason on line 60 (block 100, the holistic review, which
  said line 60).
- D10's reasons: the carve-out also leaves `asyncio.wait_for` and `asyncio.timeout` allowed, by choice
  (block 100, the holistic review).
- Section 4: block 50 passed 500 lines too, 547 (block 100, the draft).
- Section 4's transient state `expire_lost(unseen_since)`, blocks 20 to 50 (block 60).
- Acceptance 1: the grep printed migration 0011's header until block 100 reworded it, and
  `SqliteSourceRepository` also takes `node_id` and `time_between_reads`, a duration (block 100, the draft and
  the holistic review).

Beside them, D11's `(Corrected: ...)` in section 8 of `agents/specs/2026-10-13-append-only-source-points.md`:
it missed the lost-download detection, whose forward step wrote a wrong row (block 100).

## Wrap counts

Counted with `gh run list --branch <b>` on each stack branch, 2026-10-14, before block 90's run.

- **Fix-backs**: 1, block 60's `COALESCE(last_seen_at, queued_at)` (`0011b1c`), the operator's "A".
- **Cascaded rebases**: 1, block 70 onto it (`aec1e84` to `8d1e655`). `origin/main` has not moved from
  `10b45f0`, so no rebase onto it yet.
- **Runs**: #217 `38568141645`, #218 `38570150661`, #220 `38572288371`, #221 `38575020730`, #222
  `38576965981`, green at their first head; #223 `38592604829` (`ca14e4a`) then `38594192383` (`0011b1c`),
  both green; #224 `38593859149` (`aec1e84`, cancelled by the cascade), then two at `8d1e655` one second
  apart, `38594193204` cancelled and `38594196180` green; #225 `38596869012`, green. Runs re-triggered: 2
  (blocks 60 and 70), against 10 blocks; block 70's rebase push started two runs, the first cancelled at
  once.
- **Bodies the operator called unreadable**: none known at writing.

## Holistic review

`.reviews/monotonic-clock-holistic.md`, over `origin/main...origin/refactor/console-clock-lint`: 0 critical,
1 major, 9 minor. Every finding exits as fixed in the lot, in block 100:

- **MAJOR, the backoff's reload untested** (`composition/app.py`'s `load_from`): fixed,
  `test_a_backoff_the_previous_run_saved_holds_the_first_search` seeds `backoff_states` with the client's
  row, a delay of an hour, and asserts the first search waits it. With the line removed it fails on its
  own assertion: `assert (MonotonicInstant(nanoseconds=60000000000) - MonotonicInstant(nanoseconds=0)) >=
  datetime.timedelta(seconds=3600)`; the review's mutation (the line replaced by `pass`) now gives
  `1 failed, 1414 passed, 14 deselected`, where it gave `1414 passed`.
- **Acceptance 1 fails as written**: fixed, migration 0011's header names no spec and the grep prints
  nothing (exit 1); the criterion's `(Corrected: ...)` names `SqliteSourceRepository`'s `time_between_reads`,
  which Serena's `find_symbol` on each `__init__` shows beside `node_id`; `ReaderProvider` takes a path.
- **`AGENTS.md` and the spec on what `TID251` cannot see**: fixed, the rule reads "it leaves
  `asyncio.wait_for` and `asyncio.timeout` allowed and cannot see `loop.time()`"; two `(Corrected: ...)`.
- **`remaining_wait`, a function and a method**: fixed, `BackoffRegistry.time_until_retry`.
- **`backoff`, `backoff_states` and `retry_at`, two concepts each**: fixed,
  `save_backoff_states(backoff_state_by_key)` in the port, the adapter and the tests' two implementations,
  the test stub's attribute too; `LocalReader.node_state` iterates its query; `BackoffEntry.retry_at_display`.
- **`_fail_lost`'s "(spec §2; D7)"**: fixed, both parentheses dropped.
- **`reevaluation_state` missing from `local.db`'s description**: fixed, in the subgraph and the sentence.
- **`status_loop.py`'s two conventions**: fixed, the four durations are `timedelta`s, `_AlertTimer` takes
  one, `ChannelDegraded` and `ClientUnreachableLasting` convert to seconds where they are built.
- **`StatusBoard.is_current` for a client not read yet**: fixed, the branch kept as the board's contract for
  an unknown client. Its red: with the branch removed, `test_a_client_not_read_yet_is_not_current` fails
  before its assertion, `TypeError: unsupported operand type(s) for //: 'NoneType' and 'datetime.timedelta'`
  (`ports/clock.py:36`); with the branch returning `True` instead, it fails on its own assertion,
  `AssertionError: assert not True` (`test_status_loop.py:301`).
- **The handoff's spec corrections miss four**: fixed, Spec corrections above.

## Pitfalls

- **Estimates count call sites, not a diff**: every block but 60 passed its estimate, by 39 to 89 %, for the
  same reasons: a fixture or an argument added to every test of a module, and the formatter
  splitting a call that a longer name pushes past 100 columns. Block 80's 836 lines include 397 of three
  modules git counts as deleted then added (similarity under 50 %); `--find-renames=20%` gives 591.
- **A frozen fake clock dedupes and ties**: two observations at one instant share their primary key (block
  10 advances the clock between them), and a seeded decision and the next share `decided_at`, ranked by
  `id DESC`.
- **A step test must put the step where only elapsed time can tell it**: between two observations of
  `_AlertTimer`, not inside the first (block 40); and on the client, the red test measures the time slept,
  since the fake's own stamps step with the clock (block 30).
- **Mutation loops**: `git checkout` restores no untracked file, so mutations stacked (block 60); zsh does
  not split an unquoted `$VAR`, so `pytest $TESTS` ran nothing (block 70); a mutation must keep one clock per
  measure, since reading the system clock against a fake's start aborts every check at once and hides from
  the test it targets (block 90).
- **The operator's live node publishes 4711 on the development host**: a local daemon for the integration
  suites takes another port (`P2PWATCH_TEST_API_PORT`, block 40).
- **`/node`'s backoff test reads every bare `<td>`** of the page: a download seeded in `populated_app`
  would add cells to it (block 80).
- **Serena's blind spots met in this lot**, each found by `git grep`: the compose smoke's script held in a
  string (block 30); calls through `dict[str, Any]`, such as `wired["status_readings"].is_current(...)`
  (block 40); pytest fixtures injected by parameter name (block 50); a Protocol's overrides, which are not
  references (block 20); docstrings, which `rename_symbol` does not follow (block 80); a call through an
  import alias, `build_app as build_webui_app`, of which `find_referencing_symbols` lists the import line
  only (block 90); a Jinja template, `node.html`'s `entry.retry_at` (block 100). `rename_symbol` counts
  files, not sites (block 50). A parameter is renamed once per function: the port's
  `save_backoff_states(backoff)` and each implementation's are separate symbols (block 100).

## Left as is

- `migrations/local/0005_last_seen_at.sql`'s comment and `test_migration_last_seen_at.py`'s docstring name
  `expire_lost`: they give migration 0005's reason when it shipped (2026-09-13).

## Validated by CI only

- The compose smoke and arm64, every block. Blocks 30, 40, 50, 70 and 80 ran `api_integration`,
  `download_integration` and `orchestration_integration` locally against a disposable
  `ghcr.io/mission-titar/p2pwatch-amule:latest` on `127.0.0.1:14711` (6 passed each), and block 100 too,
  since it changes the status loop and the backoff's repository (6 passed); blocks 10, 20 and 60 did not,
  since none of their changes is built by those suites; block 90 did not, since `test_crawler_loop.py` runs
  with the webui off (line 101), the only wiring it changes.

## Not validated

- `local/0011` on the node's real `local.db`; the pending waits it drops cost a few early retries at most
  (`cap_seconds: 300`).
- A real clock step on a running node, or a Docker Desktop VM resyncing its clock: only `FakeTime.step_wall`
  drives the steps.
- A suspended host (section 6 of the spec): waits end late on a native Linux host, early in a KVM guest
  whose clocks jump at resume.
- `/node`'s "Backoff" section on a real node in backoff.

## Next

The operator reviews the stack, #217 to the closing block's pull request; the lead rebases it onto `main`
(`origin/main` still at `10b45f0` on 2026-10-14) and the operator merges. The lot changes the image, but
the next release still waits for the copy before a migration that rewrites rows (`BACKLOG.md`, spec
section 7).
