# Handoff: keyword-only calls

Drafted by block 170 from the lot's block reports (#561, #562, #564 to #579) and its own, corrected by the closing
block 180 with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-29-keyword-only-calls.md`, approved by the operator on 2026-10-29, with
D15 added after the holistic review (operator, 2026-10-30). It ships the `BACKLOG.md` entry "Keyword-only calls",
widened to the two kinds of call no `def` declares: a `Callable` parameter and a `NamedTuple`. Estimates by
`kwonly-estimates` and `kwonly-estimate-175` (Sonnet), spec reviewed by `kwonly-spec-review`, holistic review by
`kwonly-holistic-review`.

One stack cut from `main` at `f1b20c66`. Nineteen blocks, the closing one included: the spec's eighteen rows and
block 175, added after the holistic review.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #561 | `chore/keyword-only-rules` |
| 20 | #562 | `refactor/callback-protocols-small-packages` |
| 30 | #564 | `refactor/callback-protocols-crawler` |
| 40 | #565 | `refactor/callback-protocols-in-tests` |
| 50 | #566 | `test/clock-noqa-in-tests` |
| 60 | #567 | `refactor/ban-callable-and-namedtuple` |
| 70 | #568 | `refactor/keyword-only-checks-packages` |
| 80 | #569 | `refactor/keyword-only-amule-packages` |
| 90 | #570 | `refactor/keyword-only-vex-checks` |
| 100 | #571 | `refactor/keyword-only-domain-functions` |
| 110 | #572 | `refactor/keyword-only-domain-dataclasses` |
| 120 | #573 | `refactor/keyword-only-application` |
| 130 | #574 | `refactor/keyword-only-persistence` |
| 140 | #575 | `refactor/keyword-only-other-adapters` |
| 150 | #576 | `refactor/keyword-only-test-support` |
| 160 | #577 | `refactor/keyword-only-adapter-tests` |
| 170 | #578 | `refactor/keyword-only-core-tests` |
| 175 | #579 | `refactor/contract-ports-in-place-of-protocols` |
| 180 | the closing block's | `docs/keyword-only-calls-wrap` |

Not merged at writing. Nothing the operator sees changes (spec section 2). The image changes: every signature of `src`
past its first parameter is keyword-only, every dataclass `kw_only=True`, and the callables a component receives are
callback `Protocol`s.

## What was built

- **The rules** (block 10): ruff selects `PLR0917` with `max-positional-args = 1`; `TID251` bans `typing.override` and
  `typing_extensions.override` (D4); the ast-grep rule `dataclass-kw-only` refuses a dataclass decorator without
  `kw_only=True`, with its tests, and since block 180 a `field` whose `kw_only` is not `True`. Each zone of appendix B
  was excluded by one per-file ignore and one `ignores:` entry, and each mechanical block deleted its zone's. D3's
  `# noqa: PLR0917`s written on the 9 lines a library calls by position. `test_search_task_runner.py`'s `run_for`
  rewritten by hand as `(self, seconds, *, client, keywords, beside=())`. `AGENTS.md` gained the hard rule
  "Keyword-only calls".
- **Callback `Protocol`s** (blocks 20 to 40, D7 to D10): every `Callable` parameter of `src` (appendix A's names) and of
  the tests became a `Protocol` whose only member is `__call__`. `no-protocol-base` admits such a class (D9);
  `vulture_whitelist.py` names `_.__call__` and the parameters no code reads (D10). Each `CommandRunner` declares
  `text: Literal[True]`, and its adapter's test calls it with `text=False` under `# type: ignore[arg-type]`
  (criterion 6). `ReaderOpener` has a module of its own in `persistence_sqlite`; `NodeLoop` and `SupervisedLoop` are
  `async def __call__`, which the operator made the rule (2026-10-30, appendix B). `test_fake_files.py` admits a
  callback `Protocol` beside a double (block 40), `async def __call__` and `typing.Protocol` included (block 180).
- **`AppriseNotifier` typed** (block 30, a class 2 answer): its groups are `apprise.Apprise`, the stale "no apprise
  stubs" ignores gone, `FakeApprise` a subclass of `apprise.Apprise`.
- **Clock `noqa`s** (block 50, D11): no file is exempt from `TID251`; each of the 52 clock uses carries a bare
  `# noqa: TID251`: 6 in `src` (the 5 calls of the three clock adapters, and `search_task_runner.py`'s
  `asyncio.sleep(0)` yield), 46 in 19 test files (`git grep -n "noqa: TID251" packages`, block 180).
- **The bans** (block 60, D6): `TID251` bans `Callable` and `NamedTuple` under six names; `engine.py`'s `_RuleHit` and
  the integration conftest's `ApiEndpoint` are frozen, keyword-only dataclasses.
- **The conversion** (blocks 70 to 170, zones M1 to C7): a `*` after each first parameter (first in a test function
  or fixture), `kw_only=True` in each decorator, each caller and class pattern rewritten by keyword. Done by a stdlib
  `ast` script in the lead's scratchpad (`kwonly-block-70/kwonly.py`, its README there; block 150's version reads
  mypy's `defined in` notes). `AGENTS.md`'s examples `open(path, scripts=scripts)` and `AmuleApiClient(host,
  port=port, ...)` follow (blocks 130, 140). Block 170 deleted the last exclusion, zone C7's `PLR0917` line, with the
  comment that introduced the zones.
- **Contract ports** (block 175, D15): each of the 9 pair contracts receives a frozen, keyword-only `<Thing>Ports` of
  its two ports in place of a `Protocol` copying them, so mypy checks every call a contract makes against the ports;
  each `Test<Implementation>` builds it from its concrete fixture. `AGENTS.md`'s rule and `testing.md`'s sentence
  follow.
- **`content_hash` keyword-only** (block 180): SQLite calls the nested `content_hash_by_position`, which carries D3's
  `noqa` and names the eight columns; the store and the tests call `content_hash` by keyword. `AGENTS.md`'s rule says
  a signature a library calls by position wraps a keyword-only function our code calls too.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1730 passed, 15 deselected, from block 110 to block 175;
1736 at block 180, its 6 new `test_fake_files.py` cases).

Budgets against each parent (lines, files): 10, 125 and 12; 20, 189 and 16; 30, 121 and 15; 40, 149 and 19; 50, 59
and 24; 60, 19 and 5; 70, 504 and 71; 80, 419 and 74; 90, 384 and 40; 100, 317 and 41; 110, 2209 and 142; 120, 412
and 62; 130, 480 and 42; 140, 436 and 32; 150, 1293 and 117; 160, 633 and 42; 170, 746 and 23; 175, 487 and 29;
180, 198 and 18. The mechanical blocks pass both bounds by D14, blocks 50 and 175 the file bound (175 approved by the
operator). Blocks 110 and 150 ran 2.2 and 1.4 times their line estimate: `ruff format` splits a call past 100
columns over one line per argument once named.

Continuous integration, `gh pr checks <n> --required` (2026-10-30): `validate / gate` passes on #561, #562 and #564 to
#578. #579's run (41064429213) was in progress at writing, `build-and-verify (arm64)` pending, every other job passed.

Acceptance, at block 180's tip:

- 1: `pyproject.toml` selects `PLR0917` with `max-positional-args = 1` and holds no per-file ignore of it; a probe
  `def f(a, b)` fails `uv run ruff check <probe>`, `PLR0917 Too many positional arguments (2 > 1)`, exit 1 (block 170);
  `poe lint` exit 0. `git grep -n "noqa: PLR0917" packages` prints 10 lines: block 10's 9, `content_hash`'s now on
  `content_hash_by_position`, and `test_variants.py`'s `counting` (block 160). `ruff check packages --extend-select
  RUF100` passes, so each one is needed.
- 2: the rule holds no `ignores:`; its tests were watched failing against a stub rule (block 10:
  `FAIL dataclass-kw-only ......MMMMMM`), and on `field(kw_only=False)` before the rule's third branch (block 180:
  `FAIL dataclass-kw-only  .............MM`).
- 3: the regex prints nothing, exit 1; `pyproject.toml` bans the eight names.
- 4: `no-protocol-base`'s tests were watched failing on the two callback `Protocol`s before the rule's `not` clause
  (block 20: `FAIL no-protocol-base  ....NN........`).
- 5: no per-file ignore of `TID251`. The command as appendix C first wrote it fails, 10 `RUF100` hits on the
  `PLR0917` `noqa`s (`non-enabled: PLR0917`); with `--config 'lint.external = ["PLR0917"]'`: `All checks passed!`,
  exit 0 (block 180, `kwonly-block-170/criterion5.py` in the lead's scratchpad). Block 50 watched it fail on a
  `noqa: TID251` added to a non-clock line and on a clock `noqa` removed.
- 6: `AGENTS.md` no longer says mypy cannot check `text=True`; four tests hold `text=False` under
  `# type: ignore[arg-type]`, one per `CommandRunner`. Block 20 turned each `Literal[True]` into `bool`: mypy reported
  `Unused "type: ignore" comment` once in each.

Probes and watched failures, from the block reports:

- Block 10: a probe under `main`'s config drew only `F401`; under block 10's, `PLR0917`, `TID251 typing.override is
  banned` and `TID251 typing_extensions.override is banned`; the `@override` method `m(self, a, b)` drew no
  `PLR0917`, D4's reason. Each zone's exclusion removed alone revealed only that zone's hits (`PLR0917`: M1 66, M2 90,
  M3 49, C1a 30, C2 39, C3 37, C4 38, C5 74, C6 176, C7 118; dataclass rule: M1 31, M2 11, M3 15, C1b 78, C2 18,
  C3 2, C4 30, C5 9, C6 1).
- Block 30: `self._apprise_factory(asset)` gives `Too many positional arguments for "__call__" of "AppriseFactory"`,
  which the old `Callable[..., object]` accepted; `add(url, tags=...)` gives `Unexpected keyword argument "tags"`.
- Block 40: `test_fake_files.py` failed on the `Protocol`s beside their doubles before its `_is_callback_protocol`,
  and again with a second member added to `ReadCallback`.
- Block 50: a new `time.monotonic()` in a test passes `poe lint` on the parent, fails it on block 50.
- Block 60: a probe of nine spellings of the six banned names: nothing on the parent, 9 `TID251` hits on block 60.
- Blocks 70 to 170: no new behaviour; each zone's hits after removing its exclusions matched block 10's counts, none
  after the script. From block 110 on, a token comparison of each changed Python file before and after (dropping
  keyword names, `kw_only=True`, `*`, commas, parentheses and layout) finds no value moved or changed, and fails
  when `*` is kept (block 170: 22 files, 0 differ; with `*` kept, 22 differ). From block 130 on, a scan of every
  string literal under `packages` for a zone name followed by `(`: block 110's found the compose smoke's `_SEED_ROW`
  (the fix-back below), block 140's `_SHARED_HASHES` (rewritten), the others prose, error messages or sqlite3's own
  calls (block 170: 1 hit over 123 names, `crawler_composition.py`'s module docstring).
- Block 175: typed by the ports, the contracts drew 14 mypy errors the `Protocol` copies had passed (12
  `record_queued` taking a `str` for a `TargetId`, 2 `ClientName` indexes), fixed with the identifiers; a contract
  call by position gives `Too many positional arguments for "record_node_id" of "NodeIdWriter"`; a port parameter
  renamed in the port alone gives `Unexpected keyword argument "created_at"` on the 3 contract calls, which the
  parent's contracts did not report; removing `TestFakeNodeIdStore.node_id_ports` fails `test_contract_subclasses.py`.
- Block 180: `content_hash` made keyword-only before its wrapper: 11 tests failed and 5 errored, among them
  `test_content_hash_sql_function_matches_the_python_one` (`sqlite3.OperationalError: user-defined function raised
  exception`) and the migrations 0007 and 0008 (`MigrationError: migration 7 failed: user-defined function raised
  exception`); mypy saw none of it (`SqlFunction` is gradual). `_is_callback_protocol` refused the
  `async def __call__` and `typing.Protocol` cases before the fix (2 failed, 9 passed).

## Departures from the spec

- Block 10: the dataclass rule has no C7 entry (zone C7 holds no dataclass); C4's and C5's globs avoid a `*` in a file
  name, which ruff and ast-grep let cross a `/`; `run_for` converted there, not in block 170.
- Block 20: the `Protocol`s carry no docstring; `vulture_whitelist.py`'s header now reads "a call no rewrite can show
  vulture"; the callback sentence joins block 10's hard rule in `AGENTS.md`.
- Block 30: `ReaderOpener` in a module of its own; `NodeLoop` and `SupervisedLoop` as `async def __call__`, adopted by
  the operator and written into appendix B by block 40 (commit `b7022e99`, an addition, no `(Corrected: ...)`).
- Block 40: `FilesystemConfigChecker`'s test parametrizes the bound methods under a `ConfigCheck` `(path, /)`, since
  appendix B's unbound-method recipe does not fit its three differently named parameters (marked `(Corrected: ...)`
  by block 180); `test_fake_files.py` and `AGENTS.md` admit a callback `Protocol` beside a double; `_serve_http` takes
  Starlette's `Scope` too.
- Block 50: criterion 5's command could not pass as written (corrected by block 180); two trailing comments moved for
  the line length.
- Block 160: a tenth `# noqa: PLR0917`, `counting` (class 2 below; marked `(Corrected: ...)` by block 180).
- Block 175: `AmuleConfStoreContract` has two abstract fixtures, both returning `AmuleConfPorts`; the abstract
  fixtures' docstrings read "The ports of a store ..."; `TestAsyncioRunStateStore`'s `run_state_ports` is a plain
  `pytest.fixture` over its async `run_state_store`.
- Block 180: `content_hash`'s positional wrapper is a function nested in `register_sql_functions`, like `fold_stored`.
- Blocks 60 to 150, 170: none beyond the class 2 answers.

## Class 1 fixes

- Block 60: `no-module-patching.yml`'s note advised "a typed `Callable`"; it now says "a callback `Protocol`".
- Block 70: `packages/matching/AGENTS.md`'s pipeline sketch called `MatchingEngine` and `MatchDecision` by position.
- Block 100: two f-string messages passed 100 columns once named, each cut in two adjacent literals.
- Block 110: four `SharingPeriod(...)` constructions under `# fmt: skip` passed 100 columns once named; the marker
  went.
- Block 150: a `rows(connection, sql=...)` call passed 100 columns; its string cut in two literals.
- Block 175: the contracts' identifiers that the ports' types require (`TargetId("062A")`, `ClientName("amuled")`).
- Blocks 10 to 50, 80, 90, 120 to 140, 160, 170, 180: none.

## Class 2 questions

- Block 30: `AppriseNotifier` rested on apprise shipping no types, false today. Operator, "reco ok": fixed in block 30,
  `FakeApprise` subclassing `apprise.Apprise` (commit `94e5c179`).
- Block 130: the contracts in `tests/contracts` (zone C5) call their store through a `Protocol` of their own, still
  positional, which mypy never sets against the implementation since `pytest.fixture` erases the fixture's type: 11
  tests failed, hiding 5 more. Operator, "reco ok": the contracts' calls rewritten by keyword in block 130 (commit
  `f6a84f46`), the `Protocol`s left to block 150. Block 140 applied the same answer to `StatusReadingStoreContract`
  (commit `6245e8ad`).
- Block 160: `test_variants.py`'s local `counting(text, number)`, registered as a two-argument SQL function that
  SQLite calls by position, failed once keyword-only. Operator, option A: D3 as written, a `# noqa: PLR0917`.
- The holistic review: the contract `Protocol`s, a copy of the ports that nothing checks. Operator: block 175 added
  (D15), past the file bound.

## The holistic review

By `kwonly-holistic-review` over `git diff origin/main...origin/refactor/keyword-only-core-tests` (`f9df14b2`):
1 major, 8 minors. Each finding and its exit:

- MAJOR, `AGENTS.md` and `testing.md` claimed mypy holds each contract subclass's fixture to the contract's
  `Protocol`. Fixed in the lot: block 175 replaced the `Protocol`s by `<Thing>Ports` and rewrote both sentences, which
  now claim only what mypy checks (the contract's calls, against the ports); block 180 found no other sentence
  claiming the check (`git grep` over the living documents, the contracts and the rules). The review's backlog entry
  for a signature comparison is moot: no copy is left to compare, and the operator agreed to none.
- `content_hash`'s `noqa` left our own callers positional. Fixed (block 180).
- `_is_callback_protocol` refused `async def __call__` and `typing.Protocol`. Fixed (block 180).
- Names: `RoundCallback`, `ReadCallback`, `SleepCallback`, `StopCallback` and `LoopCallback` refused, operator: "on
  garde callback". The two `MeasuredCall`s of `coverage_checks`' tests fixed as `MeasuredModulesCall` (a mapping of
  modules) and `MeasuredModuleCall` (a module) (block 180).
- The two decorators written `frozen=True, kw_only=True`: fixed, `kw_only=True` first (block 180).
- `field(kw_only=False)` unrefused: fixed, the rule refuses a field's `kw_only` other than `True` (block 180).
- The draft's clock count: fixed. The review's own count, 5 in `src` and 47 in tests, misplaced the yield of
  `search_task_runner.py`: 52 lines, 6 in `src` and 46 in 19 test files (above).
- The stale `BLE001` `noqa` would drop the only "why": fixed, `BLE001` and `N802` removed, the line keeping
  `# Notifications never break the crawl.` (block 180).
- The spec held no `(Corrected: ...)`: fixed, five: appendix B's D3 list (`content_hash_by_position`, `counting`) and
  its unbound-method recipe, appendix C's criteria 1, 2 and 5 (block 180).

## Counts

- Fix-backs: 2. Block 110 (`3a3d8670`): the compose smoke's `_SEED_ROW` built `FileKey` by position inside a script
  string; CI failed on both architectures. Block 40: the operator's `async def __call__` line, pushed again.
- Cascaded rebases: 1, block 120 onto the fixed block 110.
- Runs re-triggered by them: 3 (blocks 110 and 120 after the fix-back, block 40 after its re-push), against 19
  blocks.
- No pull request body called unreadable.

## Pitfalls

- An exclusion overlapping another zone's hides the overlap until the other goes: remove each alone to see it
  (block 10). A ruff or ast-grep glob's `*` crosses a `/`.
- A rule test naming a rule that does not exist yet passes `ast-grep test` silently (block 10; the backlog's "A rule
  test naming no rule").
- A callback `Protocol` with one parameter makes it positional-only (`/`), else a lambda or `grp.getgrnam` does not
  fit; one listing keywords (`RouteHandler`'s `request`) binds every implementation to that name (blocks 20, 40).
- `ruff --add-noqa` appends after a trailing comment, which can pass the line length (block 50). A `# noqa: TID251`
  silences every banned name on its line (spec section 7).
- `RUF100` also reports a `noqa` naming a rule the run does not select: name such rules in `lint.external` (block 50).
- A call mypy reports but the script cannot place: one inside an f-string's replacement field (blocks 160, 170), one
  forwarded by a library (`run_in_threadpool`, `asyncio.to_thread`, `functools.partial`, reported under the
  library's name or at the wrong column), one through a bound method held in a variable (no name quoted). Read mypy's
  remaining errors after each pass and rewrite them by hand (blocks 120, 150).
- A nested call or a second call on the line of the first is reported only once the outer one type-checks, and a class
  pattern that fails hides its arm's errors: run mypy and `callers` again until clean (blocks 70 to 170).
- Helper names repeat across test modules (`_checker`, `error`, `count`): the script resolves them by the method's
  class, then mypy's `defined in` note, then the file (blocks 70, 150).
- Python held in a string and run in a container escapes mypy and the unit tests: scan string literals for each zone's
  names, class names included, since a constructor's definition is `__init__` (blocks 110, 140).
- A function a library calls by position behind a gradual type (`SqlFunction`, `uvicorn.Config`) is invisible to
  mypy; only the unit test run catches it (blocks 160, 180). A failing test that leaves a sqlite3 connection open
  makes a later one fail on its `ResourceWarning`: read the first failure first.
- A `noqa` that a library's positional call needs also lets our own callers stay positional: wrap a keyword-only
  function for the library (block 180, `content_hash`).
- `pytest.fixture` erases a fixture's type: a type a fixture's annotation promises is checked by nothing, so type
  what the test calls through instead, as the contracts' `<Thing>Ports` do (blocks 130, 175). A generator fixture is
  annotated `Iterator[X]`, but a fixture depending on it receives `X` (block 175).
- A test failing on its first line hides its later ones: run the gate again after a fix (block 130).
- A named argument can push an f-string or a long string past 100 columns, which `ruff format` cannot split; a
  `# fmt: skip` keeps a construction's long lines (blocks 100, 110, 150).
- A Bash command chaining several `grep`s can be refused by the Serena hook, and the refused command does not run.
  zsh does not split an unquoted variable: a file list in `$FILES` reaches a command as one argument (block 175).

## Not validated

- The integration suites (the compose smoke, the crawler loop, the amuleapi suites) run only in CI's `validate / gate`,
  never locally in this lot; the scripts they hold in strings were read by hand and two of them run locally with the
  crawler's interpreter (blocks 110, 140). #579's and block 180's runs were in progress at writing.
- No real node has run the converted image, nor migrated a catalog through `content_hash_by_position` (the unit tests
  migrate versions 7 and 8 through it).

## Next

The lot changes the image, by its signatures only. Whether a release follows is the lead's to propose once the stack
merges (Wrap f), under the constraint the earlier handoffs name: the v5 waits for a P2P network other than eD2k
(operator, 2026-10-27). Then `BACKLOG.md`, read before proposing.
