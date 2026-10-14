# Monotonic clock, and persistence without a clock

- Date: 2026-10-14. Status: approved by the operator (2026-10-14), after the spec review
  (`.reviews/monotonic-clock-spec.md`, 1 critical, 3 major, 13 minor, all answered).
- Tier: Spec (the operator, 2026-10-14). Operator surfaces: `local.db`'s schema and the webui's `/node` page (D8).
- Origin: `BACKLOG.md`'s "A monotonic clock for in-memory intervals and deadlines", from section 8 of
  `agents/specs/2026-10-13-append-only-source-points.md`; and the operator's request that persistence hold no
  clock, a first step toward the clean architecture the project wants.
- Evidence: the code on `main` at `10b45f0`; a literature and Linux probe (D7's sources); an inventory of the
  blocks and the spec review, with probes of mypy 2.3.1, ruff 0.16.9, sqlfluff 4.3.0 and SQLite 3.49.1
  (2026-10-14). Paths under `packages/crawler/src/p2pwatch/` unless noted.

## At a glance

- **Persistence has no clock** (D1): a repository stores the instants it is given. The three SQLite repositories
  that read `clock.now()` take a parameter named after the column instead (D6).
- **Two clock ports** (D2): `WallClock` for stamps, `MonotonicClock` for every interval and deadline kept in
  memory, its instants a `MonotonicInstant` whose arithmetic and ordering mypy will not mix with a `datetime` (D3).
- **A wait persisted across a restart stores its decided duration and its start** (D7): at restart the elapsed
  time is clamped to [0, the duration], so a clock stepped back never lengthens a wait past its own decision.
  The search backoff and the lost-download detection follow it; the latter leaves SQL for the application.
- **`local.db`'s key/value `scheduler_state` becomes a typed `backoff_states` table**, shown on `/node` (D8).
- **Only the clock adapters read the system clock, asyncio's own timeouts aside**, enforced by ruff's `TID251`
  (D10).

## 1. Why

- **The repositories decide which instant a row carries.** `SqliteCatalogRepository`, `SqliteDownloadRepository`
  and `SqliteLocalStateRepository` hold the `Clock` port and call `now()` inside their writes
  (`catalog_repository.py:123,158,182`, `download_repository.py:75,109,130,152`,
  `local_state_repository.py:47`). The use-case that decided the write does not see the instant, and every test
  of persistence must inject a clock. `SqliteSourceRepository.record_readings(file, readings, read_at)` already
  receives its instant from the use-case: the rule this lot generalises.
- **Intervals kept in memory are measured on the wall clock** (section 8 of the source points spec). Stepped back,
  the clock suspends the sources step and the amuleapi client's start pacing for the size of the step; stepped
  forward, it ends waits early, and the amuleapi client then starts an ed2k search, or a Kad search on one Kad
  word, sooner than the 60 s the networks require (`adapters/mule_api/client.py`, `_START_SPACING`).
- **Two waits are derived from a persisted wall-clock instant**: the search backoff's `retry_after` in `local.db`
  (stepped back, the wait grows by the step, with no bound), and the lost-download detection
  (`_EXPIRE_LOST`: `last_seen_at < now - lost_after`). Section 8 missed the second, and its "never a wrong row"
  is false: stepped forward past `lost_after`, the clock fails as `lost` a download absent from a single poll.

## 2. Scope

- **In**:
  - every clock consumer of the crawler package's `src/` and `tests/`, the integration suites included;
  - `local.db`'s backoff storage, and the `/node` section that shows it;
  - the lint;
  - `AGENTS.md`'s glossary and rules;
  - the texts D6 falsifies outside the crawler: `packages/matching/AGENTS.md` ("persistence columns like
    `decided_at`/`node_id` are an adapter's job") and `packages/matching/src/catalog_matching/engine.py:43-45`
    ("injected by the DB adapter");
  - the French documents each change falsifies: `docs/migration-4x.md`, `docs/operate.md` (`/node`),
    `docs/troubleshooting.md` (the lost download), `docs/contributing/architecture.md` (loss, `local.db`'s tables
    and schema version).
- **Out**:
  - the catalog's stamps and their format: `match_decisions.decided_at` stays ISO-8601 TEXT, a `BACKLOG.md`
    entry this lot adds (D12);
  - two thresholds on catalog stamps, accepted limits (D9);
  - port-sync (`packages/amule/`), a separate package that already measures its interval on `time.monotonic()`;
  - asyncio's own timeouts, which run on the event loop's monotonic time already and which `TID251` cannot see
    (D10): `asyncio.wait_for` in `adapters/observability/dispatcher.py:45`, `asyncio.timeout` and `loop.time()`
    in `composition/app.py:325-326,535`, `asyncio.to_thread(thread.join, timeout)` in `composition/app.py:386`,
    and `httpx.Timeout` in the amuleapi client;
  - the webui's read side (`BACKLOG.md`), apart from what a port change forces: `build_app`'s clock parameters
    (D2), `_client_lines` following `StatusBoard` (D5), the SQL console's clock (D10) and `/node`'s backoff
    section (D8).

## 3. Decisions

### D1. Persistence has no clock

**A repository stores the instants it is given and decides no wait.** An adapter other than persistence may
hold a `MonotonicClock` for a guard of its own I/O: the amuleapi client's start pacing and search deadlines, the
SQL console's query budget.

*Reasons: a stamp a repository picks is a decision hidden from the use-case that made the write, and a row's
instant then depends on the adapter's state. The operator first framed the clock as stopping at the use-cases,
then narrowed it to persistence (2026-10-14): pacing and deadlines are rules of a network or of an I/O call, each
client of stage 5 will have its own, and moving them into the application would teach it amuled's search
lifecycle.*

### D2. Two ports: `WallClock` and `MonotonicClock`

```python
class WallClock(Protocol):
    def now(self) -> datetime: ...  # aware, UTC

class MonotonicClock(Protocol):
    def now(self) -> MonotonicInstant: ...
    async def sleep(self, duration: timedelta) -> None: ...
```

- Injected as `wall_clock` and `monotonic_clock`. The bare name `Clock` disappears.
- `sleep` belongs to the monotonic port: `asyncio.sleep` waits on `loop.time()`, "the event loop's internal
  monotonic clock" (Python's asyncio event loop documentation).
- `sleep` takes a `timedelta`. Of its six call sites, four compute a difference of instants (`client.py:173,178,191`,
  `search_tasks.py:55`), which D3 makes a `timedelta`; the two periods (`status_loop.py:139`'s constant,
  `run_download_cycle.py:509`'s `poll_interval_seconds`) convert once.
- `Rng` leaves `ports/clock.py` for `ports/rng.py`.

*Reasons: the two clocks serve different uses, so the type injected says which time a consumer may read; the
amuleapi client receives the monotonic clock alone and cannot stamp anything. `Clock` alone would leave every
signature ambiguous ("the most telling word wins over the most widespread one", `AGENTS.md`). One method name,
`now()`, on both ports is safe because their return types differ. A `timedelta` cannot be mistaken for a count or
an instant, and spares the computed waits a `.total_seconds()` (the operator, 2026-10-14). Randomness is not time:
`Rng` gets its own module now that the clock module is rewritten.*

### D3. `MonotonicInstant`, a value type

- A frozen, ordered dataclass in `ports/clock.py` holding an `int` of nanoseconds read with `time.monotonic_ns()`.
- `instant - instant` gives a `timedelta`; `instant + timedelta` and `instant - timedelta` give an instant.
- **Never persisted, never displayed**: its origin means nothing outside the process.
- mypy refuses `instant - datetime`, `datetime - instant`, `instant < datetime` and `timedelta + instant`; it
  accepts `max(instant, datetime)`, `min` and `==` across the two (probe with `mypy --strict`), which stay for the
  reader.
- Variables holding one keep the words of a wall-clock instant: `_at`, `deadline`, `next_start`. The glossary
  gains three rows:

| Word | Means | Never |
|---|---|---|
| `wall clock` | `WallClock`, the UTC time of day: every stamp a row, an event or a display carries | an interval or a deadline kept in memory |
| `monotonic clock` | `MonotonicClock`, its `MonotonicInstant`s: every interval and deadline kept in memory | a stamp, anything persisted |
| `persisted wait` | a wait that survives a restart: its start on the wall clock and its duration, clamped by `remaining_wait` when the node meets it again | a deadline persisted alone |

*Reasons: what the type system can guarantee without absurd complexity, it should (the operator, 2026-10-14): mypy
then refuses the arithmetic and the ordering that mix the clocks, where a `float` of seconds suffixed `_monotonic`
would only ask a reviewer to notice. Integer nanoseconds keep the arithmetic exact. The variable names need no
suffix because the type carries the clock ("a quantity carries its unit unless its type does"). Go's `time`
package drops its monotonic reading from every serialized form for the same reason (https://pkg.go.dev/time).*

### D4. The adapters and the fakes

- `adapters/wall_clock_system.py`: `SystemWallClock`, `datetime.now(UTC)`.
- `adapters/monotonic_clock_asyncio.py`: `AsyncioMonotonicClock`, `time.monotonic_ns()` and `asyncio.sleep`. Its
  `now()` never asks for the running loop: the webui calls it from its own thread and loop (`StatusBoard`, the SQL
  console).
- `adapters/rng_random.py`: `SeededRng`, which keeps its name.
- `adapters/clock_asyncio.py` is deleted.
- The tests' two `FakeClock`s (`tests/application/fakes.py:20`, `test_run_download_cycle.py:290`) become one
  `FakeTime`, a fake timeline the test drives: `advance()` moves both clocks, `step_wall()` moves the wall clock
  alone (the clock step every test of this lot needs), `sleeps` records the durations asked. The code under test
  receives its two views, `fake_time.wall` (`FakeWallClock`) and `fake_time.monotonic` (`FakeMonotonicClock`,
  whose `sleep()` advances the timeline), each built by `FakeTime` with a reference to it.
  `tests/virtual_time.py`'s `LoopClock`, which runs on the event loop's virtual time, gets the same two views.
  The other stubs (`_AdvancingClock`, `_BlockingClock`, `_StubClock`) follow the port they stand for.

*Reasons: the repository's convention is `<port>_<technology>.py` and `<Technology><Port>`
(`wake_hub_asyncio.py`'s `AsyncioWakeHub`, `disk_space_shutil.py`'s `ShutilDiskSpace`); `SeededRng` keeps the name
the operator approved (2026-10-14), its seed being what a reader needs from it. One fake cannot implement both
ports, since both name their method `now()` with different return types; two views over one timeline keep a
test's time coherent.*

### D5. Every interval and deadline kept in memory moves to the monotonic clock

| Consumer | Today | After |
|---|---|---|
| amuleapi client (`adapters/mule_api/client.py`) | `_ed2k_next_start`, `_kad_next_start`, `give_up_at`, `deadline`: wall | `MonotonicInstant`s; the client receives `MonotonicClock` only; `_LONG_AGO` becomes `None` |
| sources step's gate (`DownloadDeps.sources_read_at`) | wall, one `now()` shared with `_AlertRound` | `MonotonicInstant`; `_AlertRound.started_at` and each `read_at` stay wall, since they reach the catalog |
| `StatusBoard.is_current` | wall `now()` against `StatusReading.read_at` | the board keeps the monotonic instant of each publication and `is_current` takes the client's name; `read_at` stays wall, for display; the webui's `_client_lines` follows |
| `_AlertTimer.observe` | wall `now` | `MonotonicInstant` |
| every `sleep` (search tasks, status loop, download loop, amuleapi client) | `Clock.sleep` | `MonotonicClock.sleep` |

*Reasons: section 8's analysis, plus the networks' 60 s spacing, which a forward step would break. `_LONG_AGO`
(`datetime.min`) stood for "no start yet"; a monotonic instant has no meaningful "long ago", and `None` says it
directly.*

### D6. Repositories take their instants as parameters

| Today | After |
|---|---|
| `record_observation(observation)` | `record_observation(observation, observed_at)` |
| `record_decision(file, decision)` | `record_decision(file, decision, decided_at)` |
| `record_retraction(file, target_id)` | `record_retraction(file, target_id, decided_at)` |
| `record_queued(file, target_id, size_bytes)` | `record_queued(file, target_id, size_bytes, queued_at)` |
| `set_state(file, COMPLETED)` | `record_completed(file, completed_at)`, which clears `failure_reason` as today |
| `set_state(file, state, failure_reason)` | the same, `state` typed `Literal[DownloadState.DOWNLOADING, DownloadState.FAILED]` |
| `mark_seen(statuses)` | `mark_seen(statuses, seen_at)` |
| `get_or_create_node_id()` | `get_or_create_node_id(created_at)` |
| `expire_lost(lost_after_seconds)` | removed (D7) |

- **The use-case reads `wall_clock.now()` right before each write**, as the repository did: one instant per
  observation and per decision, a re-evaluation sweep included. The dedupe of `INSERT OR IGNORE` on
  `observations` (primary key `variant_id, observed_at, source_count`) is unchanged in production.
- The composition passes `created_at`, since it calls `get_or_create_node_id` itself.
- Nothing passes `QUEUED` to `set_state` (`git grep -n -E "set_state\([^)]*QUEUED" -- packages` exits 1), so the
  `Literal` leaves it out. mypy widens a ternary over two members to `DownloadState`, so
  `run_download_cycle.py:177`'s `wanted_state` takes an explicit annotation (probed with `mypy --strict`).

*Reasons: a parameter named after its column is the rule `record_readings(..., read_at)` already follows. Only
`completed` is stamped, so splitting it out makes a forgotten `completed_at` a type error instead of a missing
column value; the `Literal` makes `set_state(file, COMPLETED)` one too. An instant carried inside
`FileObservation` or `MatchDecision` was rejected: the amuleapi mapper builds the first and has no clock, the
second comes from `catalog_matching`, a pure shared library.*

### D7. A persisted wait stores its decided duration and its start

**Rule**: a wait that must survive a restart persists `started_at` (wall clock) and its duration. When the node
meets it again, `elapsed = clamp(wall_now - started_at, 0, duration)`, `remaining = duration - elapsed`, and the
wait continues on the monotonic clock: `deadline = monotonic_now + remaining`. While the node runs, only the
monotonic clock measures it.

- A clock stepped back while the node runs changes nothing; stepped back while it is down, the wait lasts at most
  its full duration again, never more.
- A clock stepped forward while the node is down ends the wait early: no design can tell such a step from real
  downtime without an external time source, short of not counting downtime at all.
- The clamp is a pure function of the domain, `domain/persisted_wait.py`'s
  `remaining_wait(started_at, duration, now) -> timedelta`.
- On disk the start is wall, in memory the deadline is monotonic: the monotonic clock restarts from an arbitrary
  origin with each process, so only the wall clock means anything once read back.

**The search backoff** (D8's table): `record_failure` stores `started_at` and `delay` and keeps a monotonic
deadline in memory; `load_from` computes each deadline through `remaining_wait`.

**The lost-download detection** leaves SQL for the application:

- `DownloadDeps.loss_deadline_by_file` maps each non-terminal tracked download to the `MonotonicInstant` from which
  it counts as lost.
- A download queued by the running node (`record_queued` returns `True`) gets `monotonic_now + lost_after`.
- At each cycle the map is reconciled with the repository's new read `last_seen_at_by_file()` (non-terminal rows,
  their persisted wall stamp): a download the map lacks gets `monotonic_now + remaining_wait(last_seen_at,
  lost_after, wall_now)`; a download the repository no longer lists leaves the map, which covers a row the
  operator deleted for a manual retry; a download the client lists gets `monotonic_now + lost_after`.
- A download absent from the client whose deadline has passed is failed with `failure_reason` `lost` through
  `set_state`, logged as today.
- `mark_seen(statuses, seen_at)` keeps persisting `last_seen_at` for the next start. `expire_lost` and
  `_EXPIRE_LOST` are removed.
- A node down longer than `lost_after` fails, at its first cycle, every non-terminal download the client does
  not list, as `_EXPIRE_LOST` does today.

*Reasons: the persisted duration bounds the wait by its own decision, so no global maximum is assumed (the
operator, 2026-10-14). This is systemd's treatment of a persisted timer: a stamp is used "only if it is actually in
the past", and "if we appear to have triggered in the future, the system clock must have been set backwards. So
let's rewind our own clock" (https://raw.githubusercontent.com/systemd/systemd/main/src/core/timer.c). Rejected:*

- *an absolute deadline, today's design, which Redis documents as breaking under a clock step
  (https://redis.io/docs/latest/commands/expire/);*
- *persisting the remaining time and not counting downtime (Chubby, etcd's `LeaseCheckpoint`, Kubernetes' node
  controller): robust to both steps, but it needs a periodic write per wait, or else restarts each wait in full;
  for loss, 24 h at every restart;*
- *the kernel's `boot_id` with `CLOCK_BOOTTIME`: exact across a container restart, since a container shares both
  with its host (probed on Docker 29.8.1), but a Docker Desktop restart is a VM reboot, and it adds a port over
  `/proc` for a gain this project does not need.*

*Deciding that a download is lost is policy, which persistence should not hold (D1), and a monotonic deadline
cannot be compared in SQL. Reconciling the map at each cycle, rather than seeding it once when the loop starts,
gives one path for a restart, a new download and a deleted row, and lets `run_download_cycle` be tested alone.
Seeding at `record_queued` keeps a download queued by the running node off the wall clock entirely. The map holds
deadlines, as the backoff does, so the two values the reconciliation reads side by side carry two names (the
operator, 2026-10-14).*

### D8. `backoff_states`, a typed table in place of `scheduler_state`

```sql
CREATE TABLE backoff_states (
    client_name TEXT NOT NULL,
    channel TEXT,
    attempts INTEGER NOT NULL CHECK (attempts >= 1),
    started_at INTEGER NOT NULL,
    delay_seconds REAL NOT NULL CHECK (delay_seconds >= 0)
) STRICT;

CREATE UNIQUE INDEX idx_backoff_states_client_name_channel
ON backoff_states (client_name, COALESCE(channel, ''));
```

- `local/0011` creates the table and drops `scheduler_state`. The waits pending at the upgrade are lost: the backoff restarts at its base, as on a first start
  (`cap_seconds: 300.0` and `jitter_ratio: 0.3` in `deploy/crawler.yml` bound the cost to a few early retries).
- `BackoffKey(client_name, channel)`, a frozen dataclass, `channel` `None` for the whole client, replaces the
  strings `"client"` and `"client:channel"`.
- `BackoffState(attempts, started_at: datetime, delay: timedelta)` replaces `retry_after: str`.
- `started_at` is an integer of microseconds since the epoch (`micros`).
- The port `SchedulerStateRepository` becomes `BackoffStateRepository`, its modules with it;
  `load_backoff_states` and `save_backoff_states` keep their names. Saving replaces the whole table in one
  transaction, as it replaced the JSON row.
- **`/node`'s "Scheduling" section becomes "Backoff"**: one row per entry, its client, its channel or "whole
  client", its attempts, and its planned retry `started_at + delay` in UTC, as the page shows its other stamps.

*Reasons: `scheduler_state` was the MVP's key/value catch-all for the scheduler's state
(`agents/specs/2026-06-11-data-model-design.md:183`, "le plan C structurera"); `local/0006` deleted its keys, and
the backoff row the application wrote again, renamed by `local/0010`, is the one JSON row left, which nothing
validates. `STRICT` and the `CHECK`s make SQLite enforce the shape. `BackoffKey` takes the structure out of a
string for the same reason (the operator, 2026-10-14). The unique index is on an expression because SQLite treats
two `NULL`s as distinct in a unique constraint; `COALESCE` and the index's name follow sqlfluff's CV02 and the
migrations' `idx_<table>_<columns>`. Micros follow the catalog's newest tables (`source_observations.observed_at`)
and the glossary. Dropping the pending waits costs one line of SQL, against date arithmetic over JSON for a wait of
at most 6.5 minutes. `/node` showed the raw JSON row; the operator chose a readable section over none (2026-10-14), since it answers "why does
the node not search".*

### D9. Two thresholds on catalog stamps: accepted limits

- **`reappeared`** compares the round's wall-clock start to the source's latest point in the catalog
  (`application/source_alerts.py:34`): a forward step larger than `reappeared_after` raises false alerts to the
  community audience.
- **`latest_decisions` and `download_candidates`** order by `decided_at DESC, id DESC`
  (`adapters/persistence_sqlite/catalog_repository.py:63-91`): a backward step between two decisions on one file
  and target ranks the newer one older until the clock catches up, and each re-judgement meanwhile appends a
  redundant decision.

*Reasons (the operator, 2026-10-14): both need a step larger than the gap they measure, hours or days, where an NTP
correction counts in seconds; the large forward step met in practice, a Docker Desktop VM resyncing its clock as
its host wakes (https://www.docker.com/blog/addressing-time-drift-in-docker-desktop-for-mac/), is real elapsed time
during which the node did not see the source; and the catalog's stamps are its shared truth across nodes, which a
local monotonic record cannot replace. Ordering decisions by `id` alone was rejected: `merge --into` gives larger
ids to older decisions from other nodes.*

### D10. The SQL console's clock, and `TID251`

- `webui/adapters/sql_console.py`'s `run_query` receives a `MonotonicClock` for its query budget and its elapsed
  time, instead of `time.monotonic()`; `build_app` passes it. Its docstrings' "wall-clock" abort, timeout, check
  and budget (lines 8, 21, 47, 87) become the monotonic budget they are.
- `pyproject.toml`'s `[tool.ruff.lint]` selects `TID251` and bans `datetime.datetime.now`,
  `datetime.datetime.utcnow`, `datetime.datetime.today`, `datetime.date.today`, `time.time`, `time.time_ns`,
  `time.monotonic`, `time.monotonic_ns`, `time.perf_counter`, `time.perf_counter_ns`, `time.clock_gettime`,
  `time.clock_gettime_ns` and `asyncio.sleep`, each message naming the port to inject. Exempted by
  `per-file-ignores`: the two clock adapters, every `tests/` tree, and `packages/amule/`.
- `application/search_tasks.py:59`'s `asyncio.sleep(0)` yields to the loop and reads no clock: it keeps a
  `# noqa: TID251` with that reason.
- `AGENTS.md` gains the design invariant "persistence has no clock" (D1), the hard rule "only the clock adapters
  read the system clock, asyncio's own timeouts aside", and `TID251` in its ruff line.

*Reasons: the console is the one adapter reading the system clock directly (its docstring claims the right). With
it injected, the invariant holds everywhere but asyncio's timeouts, and a lint checks it on every push instead of a
reviewer (the operator, 2026-10-14). `TID251` flags a call, `datetime.now(UTC)` after `from datetime import
datetime` included, a bare reference such as `default_factory=datetime.now`, and a `from time import monotonic_ns`;
it honours `# noqa: TID251` and cannot see `loop.time()`, a method of an object (ruff 0.16.9, probed on scratch
files). `composition/app.py:326`'s `loop.time()` arms asyncio's shutdown timeout, hence the rule's carve-out.*

### D11. Adjacent defects fixed on the way

- `connection.py:60`'s `utc_iso` raises a French message ("utc_iso exige un datetime aware (contrat de Clock)"),
  against `AGENTS.md`'s language rule: English, with its docstring (line 56), naming no clock since persistence
  holds none, in block 20.
- `tests/integration/test_compose_smoke.py:449-461` builds an amuleapi client inside a Python script held in a
  string, importing `p2pwatch.adapters.clock_asyncio` and passing `clock=`: invisible to the language server and to
  mypy, run by CI on every pull request (`.github/workflows/validate.yml:155-156`). Block 30, where the client's
  constructor changes, updates it.
- Section 8 of `agents/specs/2026-10-13-append-only-source-points.md` says the wall-clock limit costs "never a wrong
  row", which the lost-download detection contradicts (section 1): the closing block adds a `(Corrected: ...)`
  beside it.

*Reason: each is class 1 (contained, obviously correct) in the change that touches it.*

### D12. `BACKLOG.md`

- Removed: "A monotonic clock for in-memory intervals and deadlines", which this lot ships.
- Added, at the operator's request (2026-10-14): "**Every stamp an integer of microseconds since the epoch**, as
  the catalog's points already are: the ISO-8601 TEXT stamps left in both databases converted; the catalog's
  waits for the copy before a migration that rewrites rows."

## 4. Blocks

Estimates from the inventory and the spec review's recount (2026-10-14, call sites counted, not a diff: read them
as plus or minus 20 %).

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `refactor/catalog-without-clock` | D6 for the catalog: `record_observation`, `record_decision`, `record_retraction`, the repository's constructor; `record_observations`, `rejudge_file`, `reevaluate_catalog`, the search worker's deps, the composition; the two `packages/matching` texts; the spec | 270, 24 |
| 20 | `refactor/downloads-without-clock` | D6 for downloads and the node's identity: `record_queued`, `record_completed`, `set_state`'s `Literal`, `mark_seen`, `get_or_create_node_id`; D11's `utc_iso` | 190, 14 |
| 30 | `refactor/monotonic-clock-client` | D2 and D3's `MonotonicClock` and `MonotonicInstant`, D4's `AsyncioMonotonicClock` and `FakeTime`, D5's amuleapi client, the composition's client factories, D11's compose smoke, the `monotonic clock` glossary row | 330, 17 |
| 40 | `refactor/monotonic-intervals` | D5's other rows: the sources gate, `StatusBoard` and `_client_lines`, `_AlertTimer`, every loop `sleep` | 200, 13 |
| 50 | `refactor/wall-clock-port` | D2's `WallClock`, D4's `SystemWallClock`, `Rng`'s move, `Clock`, `adapters/clock_asyncio.py` and both `FakeClock`s deleted, every remaining `clock` renamed, `build_app`'s included, the `wall clock` glossary row | 290, 27 |
| 60 | `refactor/loss-detection` | D7's `remaining_wait`, the `persisted wait` glossary row, the lost-download detection, its documents | 330, 12 |
| 70 | `refactor/backoff-key` | D8's `BackoffKey`, the adapter still encoding it into the JSON row | 100, 9 |
| 80 | `refactor/backoff-states-table` | D7's backoff and D8's table: `local/0011`, `BackoffState`, `BackoffStateRepository`, the registry, `/node`'s section, their documents | 540, 28 |
| 90 | `refactor/console-clock-lint` | D10 | 110, 10 |
| 100 | `docs/monotonic-clock-wrap` | the closing block: `BACKLOG.md` (D12), D11's correction of the 2026-10-13 spec | |

- **Block 10 passes 20 files**: the operator chose one block over a catalog repository left half on its clock
  (2026-10-14); most of its files are tests changed by one argument.
- **Block 50 passes 20 files** under the one-line exemption: a mechanical rename past the bounds takes the
  exemption rather than a split (the operator, 2026-10-13).
- **Block 80 passes both bounds**: the operator chose one migration and a `/node` never left empty over two blocks
  (2026-10-14).

### Order

- The repositories lose their clock first (10, 20), so the persistence tests change once; the use-cases pass the
  old `Clock.now()` until block 50 renames it.
- The monotonic clock arrives with its first consumer (30), then reaches the others (40), before the wall port
  closes the old one (50).
- Loss (60) and the backoff (70, 80) need both ports and `remaining_wait`.
- The lint (90) comes last, once no banned call is left outside its exemptions.

### Transient states inside the stack

- Blocks 30 to 40: `Clock` and `MonotonicClock` coexist, as do the old `FakeClock`s and `FakeTime`. Merging them
  away would make one block of about 820 lines and 50 files; each consumer moves once and no block leaves dead code
  (the operator, 2026-10-14).
- Blocks 20 to 50: `expire_lost(unseen_since)` takes the cut-off the download loop computes on the wall clock,
  so that the repository loses its clock in block 20; block 60 deletes it (D7). (Corrected: this state was not
  listed; block 20 met it and the operator chose it, 2026-10-14.)
- Block 70: the adapter encodes `BackoffKey` into the JSON row, about twenty lines block 80 deletes.
- Until block 90: the SQL console reads `time.monotonic()`, as on `main`.

### Surfaces whose consumer arrives in a later block

None: each port method and read arrives with its caller.

## 5. Acceptance

Each criterion names what would prove it wrong.

1. **No repository holds a clock**: `git grep -n -i clock -- packages/crawler/src/p2pwatch/adapters/persistence_sqlite`
   prints nothing (on `main` it prints the three repositories and `connection.py`), and every repository under
   `adapters/persistence_sqlite/` takes nothing in its constructor but its connection, plus `node_id` for the
   catalog (read with Serena's `find_symbol` on each `__init__`).
2. **The lint refuses a clock read**: a file under `packages/crawler/src/p2pwatch/` holding `datetime.now(UTC)` makes
   `uv run poe lint` exit non-zero with `TID251`; the same file under `packages/crawler/tests/` passes. On `main`
   the first passes. The block report quotes both runs.
3. **A clock step changes no wait kept in memory.** Each bullet's test is first written against `main`'s API,
   today's `FakeClock` moved by `advance(-3600)` or `advance(+3600)` between the two operations as the step, and
   watched failing on the bullet's own assertion, its failure line quoted in the block report; the block then
   moves it to `FakeTime.step_wall`. A test of `FakeTime` shows that `step_wall` moves `wall.now()` and leaves
   `monotonic.now()`.
   - amuleapi client: after a step of minus or plus one hour, two ed2k starts are still 60 s apart, no more, no less
     (on `main`, 3,660 s or 0 s);
   - sources gate: after a step back of one hour, the step after `sources_interval` reads the sources;
   - `StatusBoard`: after a step forward of one hour, a reading published a second earlier is current;
   - `_AlertTimer`: after a step forward of one hour, no alert before its delay of monotonic time;
   - backoff: after a step forward of one hour the key stays in backoff; after a step back of one hour it leaves
     backoff at its delay;
   - loss: with `lost_after` 24 h, after a step forward of two days, a download absent from one poll is not failed.
4. **A persisted wait is clamped by its own duration**:
   - a backoff row whose `started_at` is one hour in the future and whose delay is 300 s releases its key after
     300 s of monotonic time, not 3,900;
   - a `downloads` row whose `last_seen_at` is one hour in the future is failed after `lost_after` of monotonic
     absence, not `lost_after` plus one hour;
   - a row last seen two days ago with `lost_after` 24 h, absent at the first cycle, is failed at that cycle.
5. **The table enforces its shape**: at `local.db` version 11, `PRAGMA table_list` shows `backoff_states` with
   `strict` 1; inserting `started_at = 'x'`, `attempts = 0` or `delay_seconds = -1` raises; a second row
   `('amule-1', NULL, ...)` raises; `scheduler_state` is absent. A version 10 `local.db` holding a `backoff_states`
   JSON row migrates to an empty `backoff_states`.
6. **`/node` shows the backoff**: a seeded row renders its client, "whole client" for a `NULL` channel, its
   attempts and its planned retry in UTC.
7. **The gate**: `uv run poe check` passes at each block's tip; `uv run poe docs-build` passes where a block touches
   `docs/`; CI's compose smoke and integration suites pass on amd64 and arm64 (blocks 30, 50 and 80 change what
   they import or store).
8. **Out of scope stays out**: `git diff --name-only origin/main...origin/docs/monotonic-clock-wrap --
   packages/crawler/src/p2pwatch/adapters/persistence_sqlite/migrations/catalog packages/amule` prints nothing.

## 6. Risks and accepted limits

- **A clock stepped forward while the node is down ends a persisted wait early** (D7).
- **Two thresholds on catalog stamps** (D9).
- **asyncio's own timeouts** read the event loop's monotonic time unseen by the lint (section 2).
- **A suspended host**: on a native Linux host, `CLOCK_MONOTONIC` stops during a suspend, so a wait ends late by the
  suspend's length, and a status reading taken before the suspend reads as current until the next one, at most
  one status period after the wake: accepted. In a KVM guest whose clocks jump forward at resume
  (https://lkml.iu.edu/hypermail/linux/kernel/2104.3/01129.html), waits end early instead.
- **The backoff pending at the upgrade is lost** (D8).

## 7. Adjacent backlog items

- **Multi network, stage 5**: stays open; each new client receives a `MonotonicClock` for its pacing (D1).
- **Sort the files view by first seen**: stays open; it reads catalog stamps, untouched here.
- **A copy before a migration that rewrites rows**: stays open; this lot migrates `local.db` only, never the
  catalog. The item is required before the next release whatever it ships, so this stack is not released before
  it ships.
- **The webui in the visitor's time zone**: stays open; it concerns how stamps are displayed.
- **The webui's read side**: stays open; it inherits the console's injected clock and `/node`'s backoff section,
  both read through the existing adapters.
- **A monotonic clock for in-memory intervals and deadlines**: shipped by this lot, removed (D12).
- **Every stamp an integer of microseconds since the epoch**: added by this lot (D12).

## Appendix: pitfalls per block, for the teammates

- **Block 10**: `tests/application/test_record_observations.py:103-118` records one observation twice and expects
  two rows; with a frozen fake the primary key dedupes them, so the test advances the clock between the writes.
  `test_catalog_repository.py:131-136` and `360-366` rely on one instant on purpose. `test_search_tasks.py:132`
  builds `WorkerDeps` positionally.
- **Block 20**: the tests' `FakeDownloadRepo` (`test_run_download_cycle.py:180-253`) drives completion failures
  through `fail_set_state_for`: `record_completed` needs its own failure switch.
- **Block 30**: `tests/application/test_search_tasks.py:110,129-130` shares one `LoopClock` between the runner
  (monotonic) and the backoff registry (wall): D4's two views. The compose smoke's script is found by `git grep`,
  not by the language server.
- **Block 40**: `StatusReadings.is_current` (`ports/client_status.py:42`) and the webui's `_client_lines`
  (`webui/composition/app.py:541-561`) change with the board; the fake `_Readings` in `test_webui_app.py` too.
- **Block 50**: `composition/test_app.py` holds about twenty `factory(endpoint, clock)` definitions.
- **Block 60**: `docs/troubleshooting.md:157-176` quotes the loss log line; `docs/contributing/architecture.md:357-366`
  describes the SQL cut-off.
- **Block 80**: `test_local_migration_0010.py` imports today's repository and `BackoffState`: rewrite it in raw
  SQL, since it pins version 10. `docs/migration-4x.md:130-132` names `scheduler_state`'s key;
  `test_connection.py`'s `_LOCAL_TABLES` and `user_version`; the webui tests seed `scheduler_state`
  (`test_webui_app.py:177-181`, `test_webui_local_read.py`, `test_webui_sql_console.py:302-305,398-408`).
- **Block 90**: `test_webui_sql_console.py`'s runaway-query test can drive `FakeTime` instead of a real budget.
