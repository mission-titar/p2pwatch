# Handoff: keyword-only calls

Drafted by block 170 from the lot's block reports (#561, #562, #564 to #577) and its own, for the closing block 180
to correct with the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-29-keyword-only-calls.md`, approved by the operator on 2026-10-29. It ships
the `BACKLOG.md` entry "Keyword-only calls", widened to the two kinds of call no `def` declares: a `Callable`
parameter and a `NamedTuple`. Estimates by `kwonly-estimates` (Sonnet), spec reviewed by `kwonly-spec-review`.

One stack cut from `main` at `f1b20c66`, which had not moved when this draft was written (`git fetch`, 2026-10-30).
Eighteen blocks, the closing one included, as the spec's table plans them.

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
| 170 | block 170's pull request | `refactor/keyword-only-core-tests` |
| 180 | the closing block's | `docs/keyword-only-calls-wrap` |

Not merged at writing. Nothing the operator sees changes (spec section 2). The image changes: every signature of `src`
past its first parameter is keyword-only, every dataclass `kw_only=True`, and the callables a component receives are
callback `Protocol`s.

## What was built

- **The rules** (block 10): ruff selects `PLR0917` with `max-positional-args = 1`; `TID251` bans `typing.override` and
  `typing_extensions.override` (D4); the ast-grep rule `dataclass-kw-only` refuses a dataclass decorator without
  `kw_only=True`, with its tests. Each zone of appendix B was excluded by one per-file ignore and one `ignores:` entry,
  and each mechanical block deleted its zone's. D3's `# noqa: PLR0917`s written on the 9 lines a library calls by
  position. `test_search_task_runner.py`'s `run_for` rewritten by hand as `(self, seconds, *, client, keywords,
  beside=())`. `AGENTS.md` gained the hard rule "Keyword-only calls".
- **Callback `Protocol`s** (blocks 20 to 40, D7 to D10): every `Callable` parameter of `src` (appendix A's names) and of
  the tests became a `Protocol` whose only member is `__call__`. `no-protocol-base` admits such a class (D9);
  `vulture_whitelist.py` names `_.__call__` and the parameters no code reads (D10). Each `CommandRunner` declares
  `text: Literal[True]`, and its adapter's test calls it with `text=False` under `# type: ignore[arg-type]`
  (criterion 6). `ReaderOpener` has a module of its own in `persistence_sqlite`; `NodeLoop` and `SupervisedLoop` are
  `async def __call__`, which the operator made the rule (2026-10-30, appendix B). `test_fake_files.py` admits a
  callback `Protocol` beside a double (block 40).
- **`AppriseNotifier` typed** (block 30, a class 2 answer): its groups are `apprise.Apprise`, the stale "no apprise
  stubs" ignores gone, `FakeApprise` a subclass of `apprise.Apprise`.
- **Clock `noqa`s** (block 50, D11): no file is exempt from `TID251`; each of the 51 clock uses (5 in the clock
  adapters, 46 in 19 test files) carries a bare `# noqa: TID251`.
- **The bans** (block 60, D6): `TID251` bans `Callable` and `NamedTuple` under six names; `engine.py`'s `_RuleHit` and
  the integration conftest's `ApiEndpoint` are frozen, keyword-only dataclasses.
- **The conversion** (blocks 70 to 170, zones M1 to C7): a `*` after each first parameter (first in a test function
  or fixture), `kw_only=True` in each decorator, each caller and class pattern rewritten by keyword. Done by a stdlib
  `ast` script in the lead's scratchpad (`kwonly-block-70/kwonly.py`, its README there; block 150's version reads
  mypy's `defined in` notes). `AGENTS.md`'s examples `open(path, scripts=scripts)` and `AmuleApiClient(host,
  port=port, ...)` follow (blocks 130, 140). Block 170 deleted the last exclusion, zone C7's `PLR0917` line, with the
  comment that introduced the zones.

## Evidence

Every block's `uv run poe check` exit 0 at its tip (crawler: 1730 passed, 15 deselected, from block 110 on).

Budgets against each parent (lines, files): 10, 125 and 12; 20, 189 and 16; 30, 121 and 15; 40, 149 and 19; 50, 59
and 24; 60, 19 and 5; 70, 504 and 71; 80, 419 and 74; 90, 384 and 40; 100, 317 and 41; 110, 2209 and 142; 120, 412
and 62; 130, 480 and 42; 140, 436 and 32; 150, 1293 and 117; 160, 633 and 42; 170, 746 and 23. The mechanical blocks
pass both bounds by D14, block 50 the file bound. Blocks 110 and 150 ran 2.2 and 1.4 times their line estimate:
`ruff format` splits a call past 100 columns over one line per argument once named.

Continuous integration, `gh pr checks <n> --required` (2026-10-30): `validate / gate` passes on #561, #562, #564 to
#576. #577's run (41058577527) and block 170's were in progress at writing.

Acceptance, at block 170's tip (`cfdcf841`):

- 1: `pyproject.toml` selects `PLR0917` with `max-positional-args = 1` and holds no per-file ignore of it; a probe
  `def f(a, b)` fails `uv run ruff check <probe>`, `PLR0917 Too many positional arguments (2 > 1)`, exit 1; `poe lint`
  exit 0. `git grep -n "noqa: PLR0917" packages` prints 10 lines: block 10's 9 and `test_variants.py`'s `counting`
  (block 160, a class 2 answer; the closing block's to-dos).
- 2: the rule holds no `ignores:`; its tests were watched failing against a stub rule (block 10:
  `FAIL dataclass-kw-only ......MMMMMM`).
- 3: the regex prints nothing, exit 1; `pyproject.toml` bans the eight names.
- 4: `no-protocol-base`'s tests were watched failing on the two callback `Protocol`s before the rule's `not` clause
  (block 20: `FAIL no-protocol-base  ....NN........`).
- 5: no per-file ignore of `TID251`. The command as appendix C writes it fails: 12 `RUF100` hits, the 10 `PLR0917`
  `noqa`s (`non-enabled: PLR0917`), `BLE001` and `N802`. With `--config 'lint.external = ["PLR0917", "BLE001",
  "N802"]'` added: `All checks passed!`, exit 0 (block 170, `kwonly-block-170/criterion5.py` in the lead's
  scratchpad). Block 50 watched it fail on a `noqa: TID251` added to a non-clock line and on a clock `noqa` removed.
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

## Departures from the spec

- Block 10: the dataclass rule has no C7 entry (zone C7 holds no dataclass); C4's and C5's globs avoid a `*` in a file
  name, which ruff and ast-grep let cross a `/`; `run_for` converted there, not in block 170.
- Block 20: the `Protocol`s carry no docstring; `vulture_whitelist.py`'s header now reads "a call no rewrite can show
  vulture"; the callback sentence joins block 10's hard rule in `AGENTS.md`.
- Block 30: `ReaderOpener` in a module of its own; `NodeLoop` and `SupervisedLoop` as `async def __call__`, adopted by
  the operator and written into appendix B by block 40 (commit `b7022e99`, an addition, no `(Corrected: ...)`).
- Block 40: `FilesystemConfigChecker`'s test parametrizes the bound methods under a `ConfigCheck` `(path, /)`, since
  appendix B's unbound-method recipe does not fit its three differently named parameters; `test_fake_files.py` and
  `AGENTS.md` admit a callback `Protocol` beside a double; `_serve_http` takes Starlette's `Scope` too.
- Block 50: criterion 5's command cannot pass as written (closing block's to-dos); two trailing comments moved for the
  line length.
- Block 160: a tenth `# noqa: PLR0917`, `counting` (class 2 below).
- Blocks 60 to 150, 170: none beyond the class 2 answers.

## Class 1 fixes

- Block 60: `no-module-patching.yml`'s note advised "a typed `Callable`"; it now says "a callback `Protocol`".
- Block 70: `packages/matching/AGENTS.md`'s pipeline sketch called `MatchingEngine` and `MatchDecision` by position.
- Block 100: two f-string messages passed 100 columns once named, each cut in two adjacent literals.
- Block 110: four `SharingPeriod(...)` constructions under `# fmt: skip` passed 100 columns once named; the marker
  went.
- Block 150: a `rows(connection, sql=...)` call passed 100 columns; its string cut in two literals.
- Blocks 10 to 50, 80, 90, 120 to 140, 160, 170: none.

## Class 2 questions

- Block 30: `AppriseNotifier` rested on apprise shipping no types, false today. Operator, "reco ok": fixed in block 30,
  `FakeApprise` subclassing `apprise.Apprise` (commit `94e5c179`).
- Block 130: the contracts in `tests/contracts` (zone C5) call their store through a `Protocol` of their own, still
  positional, which mypy never sets against the implementation since `pytest.fixture` erases the fixture's type: 11
  tests failed, hiding 5 more. Operator, "reco ok": the contracts' calls rewritten by keyword in block 130 (commit
  `f6a84f46`), the `Protocol`s left to block 150. Block 140 applied the same answer to `StatusReadingStoreContract`
  (commit `6245e8ad`).
- Block 160: `test_variants.py`'s local `counting(text, number)`, registered as a two-argument SQL function that
  SQLite calls by position, failed once keyword-only. Operator, "reco ok": D3 as written, a `# noqa: PLR0917`.

## The holistic review

To come, at the head of Wrap, over `git diff origin/main...origin/refactor/keyword-only-core-tests`.

## Counts

To be completed by the closing block. Known at writing: one fix-back, block 110's (`3a3d8670`, the compose smoke's
`_SEED_ROW` built `FileKey` by position inside a script string; CI failed on both architectures). The cascaded
rebases and the runs they re-triggered are the lead's to count. No body called unreadable so far.

## The closing block's to-dos

- Appendix C criterion 5's command cannot pass as written: `RUF100` also flags a `noqa` naming a rule not selected.
  `lint.external = ["PLR0917", "BLE001", "N802"]` fixes it (block 50); correct it with `(Corrected: ...)`.
- Appendix B's D3 list gains `test_variants.py`'s `counting` (block 160), and criterion 1's "only block 10's list"
  with it, each with `(Corrected: ...)`.
- Two stale `noqa`s name rules the project never selects: `BLE001` in `observability_dispatcher.py:48` and `N802` in
  `fake_notification_sink.py:10` (block 50). Removing them drops both from the `lint.external` above.
- `BACKLOG.md`: delete "Keyword-only calls" (spec section 7); the other adjacent entries stay.

## Pitfalls

- An exclusion overlapping another zone's hides the overlap until the other goes: remove each alone to see it
  (block 10). A ruff or ast-grep glob's `*` crosses a `/`.
- A rule test naming a rule that does not exist yet passes `ast-grep test` silently (block 10; the backlog's "A rule
  test naming no rule").
- A callback `Protocol` with one parameter makes it positional-only (`/`), else a lambda or `grp.getgrnam` does not
  fit; one listing keywords (`RouteHandler`'s `request`) binds every implementation to that name (blocks 20, 40).
- `ruff --add-noqa` appends after a trailing comment, which can pass the line length (block 50). A `# noqa: TID251`
  silences every banned name on its line (spec section 7).
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
  mypy; only the unit test run catches it (block 160). A failing test that leaves a sqlite3 connection open makes a
  later one fail on its `ResourceWarning`: read the first failure first.
- A contract's `Protocol` is a second copy of a port's signature that mypy never checks against the implementation,
  since `pytest.fixture` erases the fixture's type (block 130).
- A test failing on its first line hides its later ones: run the gate again after a fix (block 130).
- A named argument can push an f-string or a long string past 100 columns, which `ruff format` cannot split; a
  `# fmt: skip` keeps a construction's long lines (blocks 100, 110, 150).
- A Bash command chaining several `grep`s can be refused by the Serena hook, and the refused command does not run.

## Not validated

- The integration suites (the compose smoke, the crawler loop, the amuleapi suites) run only in CI's `validate / gate`;
  the scripts they hold in strings were read by hand and two of them run locally with the crawler's interpreter
  (blocks 110, 140).
- No real node has run the converted image.

## Next

The lot changes the image, by its signatures only. Whether a release follows is the lead's to propose once the stack
merges (Wrap f), under the constraint the earlier handoffs name: the v5 waits for a P2P network other than eD2k
(operator, 2026-10-27). Then `BACKLOG.md`, read before proposing.
