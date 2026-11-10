# Handoff: v5 lot 4a, the ground of fault isolation (tier Spec)

Drafted by block 80's teammate from the block reports (#695, #696, #698 to #710) and the lead's facts, corrected by the
closing block, cut in four parts (90, 92, 94 and 96). Spec: `agents/specs/2026-11-09-v5-fault-isolation.md`, lot 4a of
its three (D21), under `agents/specs/2026-11-04-v5-release-readiness.md` (the umbrella), whose D12 and D13 the whole lot
4 implements.

## Current state

- **The matcher's `Condition` is `TokenExpression`** (D8, block 10): the type, the rule's field, the schema's helpers,
  pydantic's error type (`expression_shape`) and the refusal, now `exactly one token expression (all/any/not)
  expected, got [...]`. The glossary has a `token expression` line; `threading.Condition` is untouched. The word
  "condition" is free for lot 4b's `HealthCondition`.
- **The search backoff recognises its cap without computing past it** (D20, block 20): `backoff_delay` compares
  `exponent × log(factor)` with `log(cap / base)` and returns the cap without the power, so the 1025th consecutive
  failure no longer raises `OverflowError`. `search.backoff.factor` is at most 10 and `jitter_ratio` at most 1,
  refused by `validate-config` with pydantic's `Input should be less than or equal to ...`.
- **The crawl pause is gone** (D19, blocks 30, 33, 36): no `/controls/pause` nor `/controls/resume` (404 like any
  unknown control), no `PauseCrawl`, `ResumeCrawl` nor their driving ports, no "The crawl is ..." line on the
  dashboard, which keeps the restart button alone. The run state holds the shutdown request only
  (`RunStateWriter` requests it, `RunStateReader` reads and waits for it; the glossary's `run state` line says so).
  `docs/operate.md`, `docs/install.md` and `docs/contributing/architecture.md` no longer mention it.
- **A file's decisions are prepared in full, written in one transaction, then dispatched** (D20, block 40):
  `DecisionWriter.record_decisions(sequence)` replaces `record_decision`, one `BEGIN IMMEDIATE` around an
  `executemany`, and a `StoreError` writes none of them; the download loop is woken after the commit, the
  `DecisionsRecorded` event dispatched last. A failed write writes and sends nothing, and the next judgement redoes
  it all. Every store's write transaction is `immediate_transaction(connection)` (block 95): `BEGIN IMMEDIATE`
  outside the `try`, so a failed `BEGIN` rolls back no transaction its caller had open; `COMMIT` inside it, so a
  failed `COMMIT` rolls back instead of leaving the transaction open; `ROLLBACK` under `suppress(sqlite3.Error)`,
  since SQLite rolls a full disk back itself and the `ROLLBACK`'s own error would replace the cause.
- **Each port-sync round is a unit of work** (D20, block 50): `PortSyncLifecycle` keeps the not-ready and rejected
  lines, logs any other exception, a bug included, with its trace, and polls again; the process exits only on a
  `SettingsError` at start. The `Logger` port of `p2pwatch_amule` gains `error_with_trace`.
- **The stop is bounded** (D20, blocks 60 and 62): only the composition's own deadline raises
  `ShutdownDeadlineError` and exits 0 (any other `TimeoutError` exits 1); the resource stack's close is cut after
  `CLOSE_TIMEOUT_SECONDS` (5 s); `p2pwatch` has `stop_grace_period: 30s`, a test holding it above
  `shutdown_deadline_seconds` plus the close's bound as `deploy/` ships them. During the start, a plain signal
  handler in `PosixProcess` sets a flag the databases' opener reads between its steps and, through an SQLite progress
  handler on every connection of the opening (the closing block), inside the pre-migration copy, its comparison
  with an earlier copy (that copy's reader included), the migrations' block, which rolls back whole, and the reclaim,
  each raising `OpeningInterruptedError`; the connection the opening returns loses the handler. The re-evaluation
  yields before each file and reads the run state there, its fingerprint left unstored when stopped. Either way one
  line, exit 0. While the start holds the loop, the plain handler only counts the signal and writes its line with
  `os.write`; a second signal exits 1 at the loop's first turn, or as `PosixProcess` exits.
  `shutdown_deadline_seconds` is refused past 25 s, compose's grace minus the close, a test holding the bound,
  `CLOSE_TIMEOUT_SECONDS` and the grace together. `PosixProcess.is_signalled()` says a signal was received; the
  opener's parameter is `is_shutdown_requested`.
- **Each driven adapter turns its outside system's real failures into its port's declared failure** (D6, blocks 70
  to 80):
  - the webui's four SQLite readers and `open_reader`: `PersistenceError` (a `StoreError`) for a missing file or one
    that is no database; the four ports state it; an earlier pre-migration copy `open_reader` refuses is left alone
    and a new copy made (the closing block, a regression of block 70);
  - the seven writer stores (decisions, observations, source points, backoff, node id, policy fingerprint, tracked
    downloads): `StoreError`, nothing written, on a full database (`max_page_count` at its size) and a read-only one
    (`query_only`), each writer contract provoking both, `StoreError`'s docstring stating it; their four fakes skip
    the case (the closing block);
  - the SQL console: a database it cannot open is a `QueryFailure`; the pre-migration copy: any `OSError` of its
    steps is a `MigrationError`; the merge: an output it cannot open is a `CatalogCopyError`, a cleanup that cannot
    remove a file a warning;
  - a stored value no store writes (a state outside its enum, an instant past year 9999, an infinite delay, a
    negative count): `PersistenceError("a stored value cannot be read: ...")`, through `wrap_stored_value_errors()`
    on each row mapper, never around the SQL; a backoff row's decoding is `backoff_read.backoff_from_row`, beside
    `observation_read`;
  - `InaccessiblePathError`, a new domain type, is the declared failure of `FreeSpaceMeter` and `CatalogFinder`: the
    download cycle admits nothing and retries, the merge refuses in one line (`MergeError`), the opener words a full
    disk whose free space is unknown as a `MigrationError`; both compositions build the opener's meter through
    `ShutilFreeSpaceMeter`; the message names the path once, then `strerror` (`cannot examine /x: File name too
    long`); `FakeCatalogFinder` runs the `CatalogFinder` contract;
  - amuleapi: a body nested past `json.loads`'s limit is a `ClientUnreachableError` (2xx) or an error body without
    envelope; `p2pwatch_amule`'s health, gluetun and listen-port clients read it as a malformed reply;
  - the config files: a YAML document nested past the recursion limit, or holding a character YAML refuses, is a
    `BrokenInputError`, so one `ConfigProblem` of its file with no key (lot 3's path); no port gained a failure; each
    policy file is read once, parsed and fingerprinted from the same bytes (`LoadedDocument.content`), and
    `open_in_memory`'s connect is wrapped (the closing block).
- **Not yet**: no common base type of declared failures (D3, lot 4b's), no health model, no supervisor. A declared
  failure still propagates as before wherever no caller handles it.

## What was built, block by block

| # | PR | Block | Lines, files |
|---|---|---|---|
| 10 | #695 | the matcher's `Condition` renamed `TokenExpression` | 74, 10 |
| 20 | #696 | the backoff capped before computing, `factor` and `jitter_ratio` bounded | 53, 5 |
| 30 | #698 | the pause's write side: routes, buttons, use cases, `set_paused` | 266, 19 |
| 33 | #699 | the pause's read side: the loops' wait, the dashboard's state, the reader's pause half | 112, 17 |
| 36 | #700 | the pause removed from the operator pages | 11, 3 |
| 40 | #701 | a file's decisions in one transaction, then dispatched | 280, 13 |
| 50 | #702 | every port-sync round's error logged with its trace and retried | 96, 8 |
| 60 | #703 | the stop's exit codes, its bounded close, compose's grace | 143, 11 |
| 62 | #704 | a signal during the start's opening, migrations or re-evaluation | 413, 13 |
| 70 | #705 | the webui's SQLite readers and `open_reader` raise `StoreError` | 166, 19 |
| 72 | #706 | the SQL console and the copiers fail in their declared failures | 102, 6 |
| 74 | #707 | a stored value no store writes raises `PersistenceError` | 441, 18 |
| 75 | #708 | `FreeSpaceMeter`'s `InaccessiblePathError`, the cycle, the opening | 202, 18 |
| 77 | #709 | `CatalogFinder`'s `InaccessiblePathError`, the merge | 152, 10 |
| 80 | #710 | the amuleapi and YAML adapters' `RecursionError`, real transport failures | 238, 14 |
| 90 | | the stop during the start: copy, comparison and reclaim interrupted, the plain handler, the 25 s bound | 404, 15 |
| 92 | | the catalog's writer contracts: a full and a read-only database | 163, 9 |
| 94 | | local.db's writer contracts, `FakeCatalogFinder`'s contract | 197, 15 |
| 95 | | the stores' write transaction in one context manager, `immediate_transaction` (the operator's request) | 193, 7 |
| 96 | | the policy files read once, `backoff_read`, `strerror`, two comments, the records | 220, 17 |

Twenty blocks: the spec's 11 rows before the closing one, 4 from their splits, the closing block in four, and
block 95, which the operator asked for in the review of #701; the operator accepted the stack past the workflow's 19
on 2026-11-10 ("Accepté").

- **The re-cut of blocks 30, 33 and 36, by the lead**: as the spec drew them, block 30 could not pass vulture, since
  `PauseCrawl` and `ResumeCrawl` were the only callers of `set_paused` in `src` (block 33 had the mirror problem with
  `is_paused` and `wait_until_resumed`). 30 removes the write side end to end, 33 the read side end to end (the
  glossary line included), 36 the doc pages alone, kept apart so 30 stays under 20 files.
- **Four splits for the bound, the first three cut by the lead from the teammates' commits**, each commit green alone:
  - block 60 (555 lines, 22 files) into 60 (exit codes, bounded close, grace) and 62 (the signals at the start);
  - block 70 (a 706-line, 37-file draft) into 70 (the readers), 72 (the console and the copiers), 74 (stored values);
  - block 75 (estimated about 350 lines, 22 files) into 75 (the meter, the cycle, the opening) and 77 (the finder,
    the merge);
  - the closing block (984 lines in all, its fix-back included) into 90, 92, 94 and 96, committed in green
    steps on one branch, the lead cutting the branches from the SHAs.
- **Departures, per block** (the spec's `(Corrected: ...)` marks are the closing block's):
  - Block 10: the rename covers every matcher identifier, comment and message built on the word, not the type alone,
    so the glossary's "never `condition`" holds across the matcher; `.claude/rules/matching.md` says "token
    expressions".
  - Block 20: none.
  - Blocks 30, 33, 36: the lead's re-cut above. Block 33 removes the dashboard's "The crawl is ..." line rather than
    leaving a constant "running"; block 36 moves two sentences of `operate.md` to the singular, the restart being the
    only control left.
  - Block 40: no fake `DecisionWriter` exists, so none was added; the judge's failure is injected by an SQLite
    trigger on the real store. The `RuntimeError` of a file never observed already ran before any write.
  - Block 50: the `Logger` port gains `error_with_trace` (the port could carry no trace); `except Exception` in the
    application ring, which no gate rule refuses; `docs/contributing/architecture.md` section 9 updated.
  - Block 60: none.
  - Block 62, four interpretations: the opening reads a flag, the pass the run state (so the webui's restart stops it
    too); a signal during the pre-migration copy, the comparison or the reclaim waited for that step to end (fixed by
    the closing block, MAJOR 2); a block of statements under 1000 virtual machine steps each never meets the progress
    handler, commits, and the check before the reclaim catches it; a second signal inside the progress callback
    raised a `SystemExit` that `sqlite3` swallowed as an interrupt, so the start exited 0 (fixed by the closing block,
    MINOR 3).
  - Block 70: none from the row.
  - Block 72 (accepted by the lead): the console's opening failure is a `QueryFailure`, its port's only failure
    shape, not a new `StoreError`; the merge's unremovable leftover is logged and the source's failure raised.
  - Block 74 (accepted by the lead): the tests sit in each SQLite adapter's own module, not in the contracts, since a
    corrupt row exists in SQLite alone and the backoff and tracked download contracts also run fakes.
  - Block 75: the pre-migration copier's handling is tested through a stub (its stats succeed before `statvfs`, so no
    real failure reaches it); `FakeFreeSpaceMeter` and `FakeBrokenFreeSpaceMeter` join `_EXEMPTIONS`; the test
    support gains `database_opener_preparing`.
  - Block 77: `FakeCatalogFinder` joins `_EXEMPTIONS` (dropped by the closing block); the adapter's "nothing exists"
    test became the contract's `nothing` case.
  - Block 80 (accepted by the lead in Wrap): the client ports and `ConfigChecker` have no contract, so the tests sit
    in each adapter's own modules, as block 74's did (a contract would make six client fakes subclass it or join
    `_EXEMPTIONS`); nested and malformed YAML take lot 3's path, no port gaining a declared failure.
  - The closing block: the four fakes of the local writer contracts skip the full and read-only case
    (`pytest.skip`, "a fake's memory refuses no write"), the reviewer's exemption; `FakeShutdownRequestingTicker`
    joins `_EXEMPTIONS` as a stub; at the 25 s bound, a close that uses its whole 5 s ends as the grace expires.
  - Block 95: `SqliteObservationStore` opened its transaction with a deferred `BEGIN` and now takes `BEGIN IMMEDIATE`,
    which changes nothing observable, its first statement a write taking the same lock; the migrations' block (a
    deferred `BEGIN` inside its `try`, only `sqlite3.Error` caught, a failure reported at the step that ran) and the
    catalog copier's per-source copy (`ATTACH` outside the transaction, each statement's failure a
    `CatalogCopyError` naming its table) keep their own transactions, sharing the shape but not the contract; the
    failed `COMMIT` is provoked by a key declared `DEFERRABLE INITIALLY DEFERRED` rather than
    `PRAGMA defer_foreign_keys`, which each `COMMIT` resets. Class 1 fix: the observation store's docstring cited
    `connection._open`, which no longer exists.
  - Every departure above is marked `(Corrected: ...)` in the spec's section 5 table and appendix A.

## The tests watched failing

One line per new behaviour; the block reports hold every case.

| Block | Test | Failure before the code |
|---|---|---|
| 10 | `test_a_wrong_expression_token_is_refused_by_its_key` | the old `exactly one condition (all/any/not) expected` against the new message |
| 20 | `test_a_delay_past_a_floats_range_is_the_cap`, `test_a_channel_refused_past_a_floats_range_waits_its_cap` (1100 failures) | `OverflowError: (34, 'Numerical result out of range')` |
| 20 | `test_a_search_value_out_of_its_type_is_refused[backoff.factor-11...]`, `[backoff.jitter_ratio-1.5...]` | `Failed: DID NOT RAISE InvalidConfigError` |
| 30 | `test_there_is_no_such_control[pause]`, `[resume]`; the dashboard's forms | `assert 303 == 404`; `assert 3 == 1` |
| 33 | `test_dashboard_renders_the_restart_form_alone_and_no_crawl_state` | `assert 'The crawl is' not in ...` |
| 40 | `test_a_refused_second_decision_writes_none_and_the_next_judgement_redoes_them` (a trigger refusing 062B) | `assert {'062A': DecisionRecord(...)} == {}` |
| 40 | `DecisionStoreContract.test_decisions_refused_on_a_file_never_observed_are_none_written` | `AttributeError: ... no attribute 'record_decisions'` |
| 50 | `test_any_other_failure_of_a_round_is_logged_with_its_trace_and_retried_at_the_next_poll` (401, 404 at login, malformed preferences, a `RuntimeError`) | `ListenPortError: POST /api/v1/auth/login?include_token=true: 401 b''` |
| 50 | `test_another_failure_of_the_set_is_logged_with_its_trace_and_retried_at_the_next_poll` | `ListenPortError: PATCH /api/v1/preferences: 500 b''` |
| 60 | `_crawl` on a `TimeoutError` from the startup | `Failed: DID NOT RAISE TimeoutError` (it exited 0) |
| 60 | the deadline cutting a stalled logout; a close that never returns; the stop grace | `assert timed_out`; `assert <Task cancelling ...> in set()` after 5 s; `KeyError: 'stop_grace_period'` |
| 62 | `PosixProcess`, a signal while the start holds the loop | `assert False` under the loop handler alone |
| 62 | the opener, a shutdown before, during and as the migrations commit | `Failed: DID NOT RAISE OpeningInterruptedError` (three) |
| 62 | wiring, SIGTERM during the migrations of a v5 catalog; during a 400-file pass | `assert (None is not None)`; `ValueError: not enough values to unpack (expected 1, got 0)` |
| 70 | the four readers' contracts, 22 cases (missing file, not a database) | `sqlite3.OperationalError: unable to open database file`; `sqlite3.DatabaseError: file is not a database` |
| 72 | a leftover `.partial` that is a directory; a `-wal` unlinked; an `out.db-shm` directory; a 256-character output | `IsADirectoryError`; `FileNotFoundError`; `IsADirectoryError` from the `finally`; `OSError: [Errno 36] File name too long` |
| 74 | each store over a row no store writes (`'bogus'` states, tiers, networks, roles; `2**62` micros; `9e999` delays; `-1` counts) | `ValueError: 'bogus' is not a valid ...`; `OverflowError: date value out of range`; `OverflowError: cannot convert float infinity to integer` |
| 75 | `TestShutilFreeSpaceMeter`, 4 cases (removed, under a file, name too long, `chmod 0` parent) | `FileNotFoundError`; `NotADirectoryError`; `OSError: [Errno 36]`; `PermissionError: [Errno 13]` |
| 75 | a full disk whose free space cannot be measured (`max_page_count = 8`, the directory renamed under the connection) | `InaccessiblePathError: free space of .../data unknown` (raw `FileNotFoundError` on `main`) |
| 77 | `TestFilesystemCatalogFinder`, 2 cases (name too long, `chmod 0` parent) | `OSError: [Errno 36] File name too long`; `PermissionError: [Errno 13]` |
| 80 | `load_yaml` on 1000 nested flow sequences, flow mappings, block sequences; through `FilesystemConfigChecker` too | `RecursionError: maximum recursion depth exceeded` |
| 80 | `load_yaml` on `a: 1\x01` | `yaml.reader.ReaderError: unacceptable character #x0001: special characters are not allowed` |
| 80 | `status()` and `error_from_response` on 100 000 nested arrays or objects; the same in `p2pwatch_amule`'s four readers | `RecursionError: maximum recursion depth exceeded while decoding a JSON array from a unicode string` |
| 80 | `test_amule_api_client_transport.py`: a reset, a close without answer, a timeout, a refused port, on loopback sockets | passed at once; `_send`'s `except` narrowed: `httpx.ReadError`, `httpx.RemoteProtocolError`, `httpx.ReadTimeout`, `httpx.ConnectError` |

Passed at once and kept as guards: block 20's `test_a_backoff_at_its_upper_bounds_is_accepted` (factor 10,
jitter_ratio 1), block 72's console `not a database` case (a query's error already), block 80's transport tests.

## The holistic review's findings and their exits

`.reviews/v5-lot4a-holistic.md`: 3 MAJOR, 10 MINOR, no CRITICAL. Every finding exits fixed in the lot, as the lead and
the operator settled on 2026-11-10 (MINOR 10: the operator's "Ok" to the lead's recommendation).

| # | Finding | Exit |
|---|---|---|
| MAJOR 1 | block 70's regression: an earlier copy `open_reader` refuses raised `PersistenceError` past `_same_content`, refusing the start | fixed, block 90: `_same_content` catches `PersistenceError` too; a directory under the copy's name is left alone, a new copy made |
| MAJOR 2 | a stop during the pre-migration copy, its comparison or the reclaim waited for the step's end | fixed, block 90: the progress handler on every connection of the opening from its start, the earlier copy's reader included, removed once returned; `SQLITE_INTERRUPT` from each step is `OpeningInterruptedError`; a test per step in the opener's module, two in the copier's |
| MAJOR 3 | no writer contract provoked a full or read-only database | fixed, blocks 92 and 94: one case per writer contract, both refusals on SQLite, `StoreError` and nothing written; the fakes skip it |
| MINOR 1 | block 80's two departures unaccepted | accepted by the lead; marked in appendix A, block 96 |
| MINOR 2 | `open_in_memory` unwrapped; `load_config` read the policy files twice, a latent stale fingerprint | fixed, block 96: one read, parsed and fingerprinted; `open_in_memory` wrapped |
| MINOR 3 | the plain handler printed and raised at any bytecode | fixed, block 90: count and `os.write`, the forced exit at the loop's first turn |
| MINOR 4 | one name, `is_shutdown_requested`, for a signal and the run state | fixed, block 90: `PosixProcess.is_signalled()`, the opener's `is_shutdown_requested`; no glossary line, the names now distinct |
| MINOR 5 | `InaccessiblePathError`'s messages repeated the path | fixed, block 96: `strerror` in the finder and the meter |
| MINOR 6 | `backoff_from_row` shared from a store's module | fixed, block 96: `backoff_read.py` and its own tests |
| MINOR 7 | `FakeCatalogFinder` exempted though it plays the contract | fixed, block 94: `TestFakeCatalogFinder`, the exemption dropped |
| MINOR 8 | `(I2)` and `(spec §7)` tags | fixed, block 96: the reason said in place |
| MINOR 9 | the MVP spec's grammar names a rule's body `condition` | fixed, block 96: a `(Corrected: ...)` mark there |
| MINOR 10 | `shutdown_deadline_seconds` accepted past compose's grace | fixed, block 90: refused past 25 s, its message naming the grace; the drift test kept, a second one holding the bound |
| marks | section 5's table, appendix A, section 6 "For lot 7" | fixed, block 96: every mark the review's "Spec conformance" lists, the closing block's split included |

The numbering follows the review's table, MINOR 1 to 10 in its order; the lead's brief counted the review's rows
from 1 to 13, so its "MINOR 5" is MINOR 2 here and its "MINOR 13" MINOR 10.

Each new behaviour's test, watched failing (or proven able to fail where it passed at once):

| Block | Test | Failure |
|---|---|---|
| 90 | `test_a_candidate_that_cannot_be_opened_is_not_reused` | `PersistenceError: disk I/O error` |
| 90 | the opener: a shutdown during the copy, during the comparison | `the opening of ... stopped` where `the pre-migration copy of ... stopped` was expected (the step ran to its end) |
| 90 | the opener: a shutdown during the reclaim | `Failed: DID NOT RAISE OpeningInterruptedError` |
| 90 | the copier: its connection, its candidate interrupting | `PersistenceError: interrupted`; `MigrationError: ... not created: File exists` (the interrupted comparison read as an unreadable copy) |
| 90 | `test_a_shutdown_requested_once_opened_interrupts_no_statement` | passed at once, the guard of the handler's removal |
| 90 | `test_a_copy_sqlite_refuses_raises_persistence_error` | passed at once, the copy's non-interrupt path |
| 90 | `test_a_second_signal_inside_a_progress_handler_raises_nothing_there_then_forces_the_exit` | `sqlite3.OperationalError: interrupted` |
| 90 | `shutdown_deadline_seconds` at 25.001; the bound's drift test | `Failed: DID NOT RAISE InvalidConfigError`; `ImportError: cannot import name 'MAX_SHUTDOWN_DEADLINE_SECONDS'` |
| 92, 94 | the seven writer contracts' refused write, full and read-only (14 cases) | passed at once, as the review expected; the refusal made a no-op: `Failed: DID NOT RAISE StoreError` (14); `wrap_sqlite_errors` made a pass-through: `sqlite3.OperationalError: database or disk is full` (7) and `attempt to write a readonly database` (7) |
| 94 | `TestFakeCatalogFinder` | the exemption dropped without it: `{'...fake_catalog_finder.py::FakeCatalogFinder': 'TestFakeCatalogFinder'}` |
| 95 | the five `immediate_transaction` tests | at collection, `ModuleNotFoundError: No module named 'p2pwatch.adapters.driven.persistence_sqlite.immediate_transaction'`; then each mutation fails exactly one: `ROLLBACK` unsuppressed, `^database or disk is full$` met `cannot rollback - no transaction is active`; `COMMIT` in an `else`, `assert not True` on `in_transaction`; `BEGIN` in the `try`, `assert False` on `in_transaction`; `except Exception` for `BaseException`, `assert not True` on `in_transaction` |
| 96 | `test_each_policy_file_is_read_once_its_fingerprint_that_of_the_bytes_parsed` (each policy file a FIFO yielding its bytes once) | `assert [] == ['f6ab2e31...']`, the second read waiting for a writer |
| 96 | the finder's and the meter's messages | `"cannot exami...cccc'" == 'cannot exami...name too long'`; `"free space o...removed'" == 'free space o... or directory'` |
| 96 | `backoff_read`'s own tests | the stored-value case moved from the store's module; `open_in_memory`'s wrap has no provokable failure |

## Accepted limits

The spec's section 6, plus:

- **At the 25 s bound, a close that uses its whole 5 s ends as compose's 30 s grace expires** (the closing block):
  the bound is the operator's decision, the deadline and the close summing to the grace.
- **A second signal while the start holds the loop in a step that never yields** (the config's parse) exits only at
  the loop's first turn (the closing block); the opening's long steps are interrupted by the first signal.
- **A copy interrupted mid-`VACUUM INTO` leaves its `.partial`**, which the next start deletes.
- **Not converted, no real failure reaching them**: `_check_catalogs`' `create_function` (short
  of memory exhaustion, block 72); the coverage reader's and the files page's tier decodes, which their SQL filters
  (block 74); a `TypeError` from a stored value of the wrong type (local.db's tables are all `STRICT`, the catalog's
  `match_decisions` and source tables too; the others' strictness not verified, block 74); the non-strict
  `Path.resolve()`, which raised on no probed path on 3.13 (block 77).
- **Found by reading, not provokable without a stub or the environment** (block 80): `httpx.AsyncHTTPTransport()`
  raises `FileNotFoundError` when `SSL_CERT_FILE` names a missing file (probed in a subprocess), which lot 4b will read
  as a `Bug`. Verified as raising nothing: `httpx.AsyncClient(...)` with a
  transport given (no proxy variable read, the base URL a constant), `aclose()` (httpcore 1.0.9 and anyio 4.15.1
  swallow a closing socket's `OSError`), tokens amuleapi could mint badly (h11 refuses the header, a
  `ClientUnreachableError`).
- **A notification is still lost if the process dies between a decision's commit and its send** (block 40, the
  spec's limit).

## For lot 7 (the operator pages, umbrella D19)

The spec's section 6 lists what the pages must say. The blocks add:

- **Two new bounds, a breaking change for a 4.x `crawler.yml`** (block 20, missing from the spec's section 6):
  `search.backoff.factor` at most 10, `search.backoff.jitter_ratio` at most 1, refused as
  `search.backoff.factor: Input should be less than or equal to 10`.
- **The matcher's renamed message** (block 10, missing from the spec's section 6): `exactly one token expression
  (all/any/not) expected, got [...]`, where 4.x and lot 3 printed `exactly one condition ...`.
- **`stop_grace_period` and `shutdown_deadline_seconds` go together** (block 60): the grace (30 s) must stay above the
  deadline plus the close's 5 s bound; `shutdown_deadline_seconds` is refused past 25, `Input should be less than or
  equal to 25: past it, deploy/compose.yml's stop_grace_period (30s) kills the crawler before its close ends` (the
  closing block), breaking for a 4.x `crawler.yml` above it; `docs/settings.md`'s bounds table still gives it a
  day.
- **A stop during the start** (block 62, the closing block): one line naming the step (the pre-migration copy, the
  migrations, the reclaim) and the version the database was left at, exit 0, a second signal exit 1; the next start
  replays an interrupted re-evaluation and deletes an interrupted copy's `.partial`.
- These, block 20's bounds, block 10's message and block 80's refusals are in the spec's section 6 "For lot 7",
  marked by the closing block.
- **The port-sync's errors in its log, with their trace** (block 50); `docs/migration-4x.md` and the operator pages
  were left untouched (the contributor page's section 9 was updated).
- **New refusals of a config file**: `invalid YAML: nested too deeply`, and a control character's
  `invalid YAML: unacceptable character #x0001: special characters are not allowed in "<unicode string>", position N`
  (block 80).
- **The pause's removal in the migration guide** (blocks 30 to 36): the operator pages no longer mention it, the
  guide is lot 7's.

## The lot's counts

- Fix-backs: 2. Block 62: its SIGTERM-during-a-pass wiring test timed out on CI, run 42709632641, judging against the
  shipped `targets.yml` at about 45 ms a file under coverage; fixed in `88b30768` by a one-target `targets.yml`,
  green on run 42715415304. Block 90: runs 42742160739 to 42742184288 failed `build-and-verify` on both arches, the
  orchestration integration test's `crawler.yml` setting `shutdown_deadline_seconds: 30.0`, which block 90's 25 s
  bound refuses; fixed in `262023f1` with the shipped 10 s.
- Cascaded rebases: 2 (blocks 70 to 74 onto block 62's fix, by hand with `git rebase --update-refs`, since
  `gh stack rebase --upstack` refuses branches not yet pushed; blocks 92 to 96 onto block 90's fix, by
  `gh stack rebase --upstack`). Runs re-triggered by them: 1 (block 62's; none for 70 to 74, not yet pushed then),
  then 4 for 90 to 96 after block 90's fix-back, and 1 for 96 rebased onto block 95 (95's own first run aside): 6 in
  all, against 20 blocks. Block 96's rebase onto 95 conflicted on `sqlite_backoff_state_store.py`, both sides kept.
- Rebases onto `main`: none so far. Bodies the operator called unreadable: none so far.
- Splits: 4 (60 in two, 70 in three, 75 in two, the closing block in four), and the lead's re-cut of 30, 33, 36.
- Blocks inserted: 1 (block 95, the operator's request in the review of #701); 20 blocks, accepted.
- Class 2 questions: 1 (block 75: one common declared failure for `FreeSpaceMeter` and `CatalogFinder`,
  `InaccessiblePathError`; the operator answered "Ok" to the recommendation on 2026-11-10).
- Class 1 fixes: 6 (block 95: the observation store's docstring citing `connection._open`; block 40: `record_decision`
  named in `docs/contributing/architecture.md`'s diagram, the glossary's `dated decision` line and an `engine.py`
  docstring; block 72: the merge's `destination.exists()` leak, not in the inventory; block 74: the backoff row's
  decoding, duplicated between two stores, one `backoff_from_row`; block 80: the control character's `ReaderError` in
  `load_yaml`, and `RecursionError` in `p2pwatch_amule`'s three JSON readers).
- The closing block: one fix-back (block 90, above), no class 1 fix, no class 2 question.
- Spec corrections: every mark the review lists, written by the closing block (block 96).

## Pitfalls learned

- **The integration suites run outside the local gate**: `uv run poe check` deselects them, so a new bound on a
  config key must be checked against every config the tests write (`git grep -n <key>` over `packages/*/tests`
  and `tests/`), the orchestration test's own `crawler.yml` included (block 90's fix-back).
- **Serena**: `rename_symbol` does not follow a dataclass's keyword argument nor a name inside a PEP 695 `type`
  alias's body (block 10); `find_referencing_symbols` misses the keyword arguments of a dataclass field (block 33); a
  rename from the port after edits made outside Serena wrote at shifted offsets, corrupted two files and left about
  15 call sites (block 40, restored from git, renamed with `sed -w`). Confirm with `git grep -n -w`.
- **vulture sets the cut**: a port method whose only callers leave in a block fails the gate, which forced the re-cut
  of 30, 33, 36; `_unit-coverage-check` likewise refuses a module that loses its own tests.
- **PLR0917**: a pytest fixture taking two parameters makes them keyword-only (block 70); `asyncio.start_server`'s
  two-positional callback is adapted through a lambda to keyword-only handlers (block 80). `collections.abc.Callable`
  is banned: a callback `Protocol`, whose lambdas must name their parameters after it, since mypy refuses `_`.
- **`ruff format` splits an `except Exception as error:  # comment`** past the line length into a parenthesised
  tuple: keep the comment short (block 50).
- **`uv run poe check` does not build the docs site**: `uv run poe docs-build` does (blocks 36, 50).
- **CI is about twice as slow as a local run under coverage** (block 62's fix-back): a wiring test judged against
  the shipped `targets.yml` passed in 10.02 s locally against a 10 s bound.
- **SQLite counts progress steps per statement**: a statement under 1000 virtual machine steps never meets a progress
  handler (block 62).
- **On Python 3.13, `Path.exists()` raises** for a name too long or a path behind a directory it cannot search
  (3.14 swallows both) (blocks 72, 77).
- **A `chmod 0` test is meaningless as root**: `skipif(os.geteuid() == 0)`; CI runs as the non-root `runner`. A
  directory where a file is expected provokes a filesystem failure under root too; on macOS `unlink` of a directory
  raises `EPERM`, not `EISDIR` (blocks 72, 75, 77).
- **`json.loads` gives up at the C recursion limit** (9998 levels on 3.13), not `sys.getrecursionlimit()`; PyYAML's
  pure-Python composer at the Python limit, below 500 levels. The tests nest 100 000 JSON levels and 1000 YAML ones
  (block 80).
- **pydantic refuses a token expression past depth 127** ("maximum validation depth exceeded"); the engine evaluates
  depth 127 under a recursion limit of 400 (block 80's probe).
- **`gh stack rebase --upstack` refuses branches not yet pushed**: the lead cascaded with `git rebase --update-refs`.
- **`PRAGMA max_page_count` alone fails no small write**: a row fitting a page's free space needs no new page, so a
  "full" database refuses only a write needing room; the contracts write a 64 Ki-character value (closing block).
- **`sqlite3.ProgrammingError` has no `sqlite_errorcode`** (a closed connection): reading it raises
  `AttributeError`; the code reads it only on errors SQLite itself raised.
- **`os.write(2, ...)` escapes `capsys`**: a test reading `PosixProcess`'s lines takes `capfd`.
- **A test double outside `tests/fakes` fails `test_fake_files`**, even private in `tests/support`.
- **zsh does not split a variable**: a list of test paths goes in an array (`"${T[@]}"`).
- **`ast-grep/tests/reader-verbs-test.yml` and `writer-verbs-test.yml`** use `is_paused`, `wait_until_resumed` and
  `set_paused` as made-up examples; `WaitingReason.PAUSED` is aMule's download state: neither is the crawl pause.

## Not validated

- No Docker integration suite was run locally by any block, the compose smoke test and the amuleapi suite included,
  but `orchestration_integration` after block 90's fix-back (1 passed, against a throwaway
  `ghcr.io/mission-titar/p2pwatch-amule:latest`, not an image built from the tree); continuous integration runs the
  compose smoke test.
- Nothing ran against a real node: the decisions' transaction (block 40), the port-sync's rounds under the VPN
  (block 50), a stop during a real migration of the operator's catalog (block 62).
- The matching comparison on the real catalog (the spec's "what must not change" row), for block 10's rename: the
  gate's golden corpus gives the same decisions.
- What the webui shows for a reader's `StoreError` (a 500, as for the raw error before; block 70): lots 4b and 4c's.
- A real stop during the operator's 380 s copy or 225 s migration: the closing block's tests interrupt each step on
  small databases only.

## Next step

The lead rebases the stack onto `main` if it moved; the operator reads and merges it. No release: v5 ships after lots 4
to 7 and the release candidates. Lot 4b next, the health model running (the spec's section 5, 14 blocks plus its closing
one), starting with `DeclaredFailure`, the base type every port's declared failure derives from (D3), on the ground this
lot laid: no pause to handle, no leak taken for a bug.
