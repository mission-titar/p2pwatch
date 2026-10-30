# Keyword-only calls

Tier Spec. Discussed with the operator on 2026-10-29. Ships the `BACKLOG.md` entry "Keyword-only calls", widened
to the two kinds of call no `def` declares: a `Callable` parameter and a `NamedTuple`.

The body reads in five minutes. The appendices hold what the teammates need: names, recipes, commands and counts.

## 1. In short

A call that passes two values by position can swap them silently when both have one type: two dates, two integers,
two booleans. The identifiers' types caught the swaps between identifiers; this lot closes the rest. Every value past
the first is named at the call, so a reader sees which parameter it goes to, and a swap no longer type-checks.

Four kinds of call carry values. Each gets its own mechanism, held by a tool of the gate:

| Call | Becomes | Held by |
|---|---|---|
| a function or method | keyword-only past its first parameter | ruff `PLR0917` |
| a dataclass | `kw_only=True` | a new ast-grep rule |
| a `NamedTuple` | a keyword-only dataclass | ruff `TID251` (banned) |
| a `Callable` parameter | a callback `Protocol` with named parameters | ruff `TID251` (banned) |

## 2. What the operator will see

Nothing: no page, metric, notification, config key or database changes.

## 3. Decisions

- **D1. A signature takes at most one positional parameter, `self` and `cls` aside, in `src` and `tests` alike.**
  *A `*` refuses a positional call outright. Test functions follow too: pytest passes fixtures by name, so one rule
  covers everything (operator).*
- **D2. One positional parameter stays allowed, not zero.** *At zero, every one-parameter function a library calls
  by position would break: `__eq__`, a web endpoint, a sort key.*
- **D3. A signature a library calls by position keeps a `# noqa: PLR0917`.** *We cannot rewrite the library's
  call. There are a handful today (appendix B).*
- **D4. `@override` is banned.** *ruff exempts an `@override` method from the rule, so one decorator would let a
  positional signature back in unseen.*
- **D5. Every dataclass is `kw_only=True`, one-field ones included.** *A dataclass's constructor is a signature too;
  ruff has no rule for it, so an ast-grep rule holds it, with no exception to remember.*
- **D6. `NamedTuple` is replaced by keyword-only dataclasses, then banned.** *A tuple's constructor cannot be
  keyword-only. Only two exist, and neither is used as a tuple.*
- **D7. `Callable` is replaced by callback `Protocol`s, then banned.** *A `Callable` cannot name its parameters, so
  a call through one stays positional. A `Protocol` names them, and mypy then checks the keywords passed: it refuses
  `text=False` where `text=True` is required, a check `AGENTS.md` says mypy cannot make today.*
- **D8. A callback `Protocol` is named after what one of its instances is**, like any class: the one doing the action
  (`CommandRunner`, `OwnerChanger`) or the thing called (`NodeLoop`, `SqlFunction`). *`subprocess.run` is a command
  runner, a node's loop function is a node loop; `AGENTS.md`'s rule for class names covers both (operator). The names
  are in appendix A.*
- **D9. The rule refusing a `Protocol` base admits a class whose only member is `__call__`.** *The rule keeps ports
  as ABCs the language server can follow; a callback `Protocol` is not a port (operator).*
- **D10. vulture's whitelist names `__call__`, and each `Protocol` parameter no code reads.** *vulture matches names,
  so it cannot see a call made through a parameter; no rewrite can show it such a call, which is what the whitelist
  is for.*
- **D11. `TID251` applies everywhere; each clock use in a test, or in a clock adapter, carries a bare
  `# noqa: TID251`.** *An exemption by file covers the whole rule, so it would also let `Callable` in. By line, a new
  clock use in a test is refused by default. The line or the double's name says why, so the `noqa` needs no comment
  (operator).*
- **D12. A call to a library keeps the library's signature.** *The rule is about our definitions.*
- **D13. The rules are on from the first block, with the code not yet converted excluded zone by zone; each
  mechanical block converts one zone and removes its exclusion.** *The gate then checks every mechanical block, and
  the last one leaves no exclusion.*
- **D14. The mechanical blocks pass both size bounds, and four non-mechanical ones reach 20 files** (operator).
  *A change of style across the code reads as one pattern; cutting it by file count buys no readability.*
- **D15. A pair's contract receives its two ports, each typed by its port, in place of a `Protocol` copying them.**
  *The copy was checked by nothing: `pytest.fixture` erases the fixture's type, so a port changed under it went
  unseen by mypy (block 130). Typed by the ports themselves, every call the contract makes is checked against them.*
  (Added after approval: found by the holistic review, operator 2026-10-30.)

## 4. Acceptance

Each criterion's command is in appendix C.

1. ruff refuses a signature with two positional parameters, and no code is excluded from that rule any more.
2. The dataclass rule refuses a dataclass without `kw_only=True`, and no code is excluded from it any more.
3. No `Callable`, `NamedTuple` or `override` is imported anywhere, and `TID251` refuses every spelling of them.
4. The `Protocol` rule admits a callback `Protocol` and still refuses a port written as a `Protocol`.
5. No file is exempt from `TID251`, and every `# noqa: TID251` sits on a clock call.
6. mypy refuses `text=False` on every `CommandRunner`, and a test keeps that refusal checked.

## 5. Blocks

Estimates by `kwonly-estimates` (Sonnet, 2026-10-29); the zones are in appendix B.

| # | Branch | Holds | Lines, files |
|---|---|---|---|
| 10 | `chore/keyword-only-rules` | the rules on, every zone excluded; D3, D4 | 110, 11 |
| 20 | `refactor/callback-protocols-small-packages` | D7 to D10 in the small packages | 145, 20 |
| 30 | `refactor/callback-protocols-crawler` | D7 in the crawler's `src` | 220, 28 |
| 40 | `refactor/callback-protocols-in-tests` | D7 in every `tests` | 190, 20 |
| 50 | `test/clock-noqa-in-tests` | D11 | 60, 23 |
| 60 | `refactor/ban-callable-and-namedtuple` | D6, the bans | 31, 4 |
| 70 | `refactor/keyword-only-checks-packages` | zone M1 | 337, 68 |
| 80 | `refactor/keyword-only-amule-packages` | zone M2 | 317, 72 |
| 90 | `refactor/keyword-only-vex-checks` | zone M3 | 240, 38 |
| 100 | `refactor/keyword-only-domain-functions` | zone C1a | 186, 40 |
| 110 | `refactor/keyword-only-domain-dataclasses` | zone C1b | 998, 140 |
| 120 | `refactor/keyword-only-application` | zone C2 | 310, 60 |
| 130 | `refactor/keyword-only-persistence` | zone C3 | 297, 40 |
| 140 | `refactor/keyword-only-other-adapters` | zone C4 | 291, 28 |
| 150 | `refactor/keyword-only-test-support` | zone C5 | 938, 116 |
| 160 | `refactor/keyword-only-adapter-tests` | zone C6 | 486, 40 |
| 170 | `refactor/keyword-only-core-tests` | zone C7; drafts the handoff | 559, 22 |
| 175 | `refactor/contract-ports-in-place-of-protocols` | D15 | 470, 29 |
| 180 | `docs/keyword-only-calls-wrap` | closing: the holistic findings, `BACKLOG.md`, the handoff | |

- **Blocks 10 to 60 hold the decisions** and come first. Blocks 20 to 50 reach 20 files (D14).
- **Blocks 70 to 170 are mechanical** (D14): they apply appendix B's recipe and nothing else.
- **Block 175 holds D15** and is not mechanical; it passes 20 files, approved by the operator (2026-10-30).

The order: the rules first, so the gate checks every later block; the `Protocol`s and the clock `noqa`s before the
bans that need them; then the conversion, from the small packages to the crawler, its `src` before its tests.

## 6. Documents

- `AGENTS.md`: each convention lands in the block that first applies it, so the file stays true at every block
  (appendix B).
- `docs/`: nothing; no page names these rules.

## 7. Limits and scope

### Accepted limits

- **A `# noqa: TID251` silences every banned name on its line.** *A clock call and a type annotation seldom share a
  line, and review sees it.*
- **The `SqlFunction` `Protocol` checks nothing of its arguments.** *SQLite passes as many as the SQL does; no static
  type can say how many.*
- **`FreeBytesMeter` and the port `FreeSpaceMeter` name one concept twice.** *Merging them changes a component's
  dependencies, outside this lot.*

### Adjacent backlog items

- "Keyword-only calls": shipped, deleted by the closing block.
- "A generic way to write the tests' stubs and spies": a double of a callback `Protocol` is one more class it would
  replace; it stays open.
- "Adopt ty": ty must check callback `Protocol`s as mypy does; it stays postponed.
- "A rule test naming no rule fails the gate": the new rule's tests name their rule; it stays postponed.
- "Test quality", "Mutation testing in the gate", "Contract tests for the fakes of outside systems", "Every catalog
  table STRICT", "Round-trip contracts", "The Grype scan back on p2pwatch", "Multi network", "Sort the files view by
  first seen", "The webui in the visitor's time zone": unrelated; they stay open.

## Appendix A. The callback `Protocol`s of `src`

Agreed by the operator on 2026-10-29. The teammates name the ones in `tests` by the same rule.

| Parameter (where) | `Protocol` | Call |
|---|---|---|
| `run_command` (three `p2pwatch_amule` adapters, `GrypeVulnerabilityScanner`) | `CommandRunner`, one per adapter | `(args, /, *, check, text: Literal[True], ...)` |
| `find_group`, `find_user`, `_is_missing` (`PosixAccountProvisioner`) | `AccountFinder`, one for both | `(name, /)` |
| `change_owner` (`PosixAmuleConfStore`, `PosixAmuledDirectoryPreparer`) | `OwnerChanger` | `(*, path, uid, gid)` |
| `transport_factory` (`AmuleApiClient`) | `TransportFactory` | `()` |
| `apprise_factory` (`AppriseNotifier`) | `AppriseFactory` | `(*, asset)` |
| `free_bytes` (`SqlitePreMigrationCopier`) | `FreeBytesMeter` | `(path, /)` |
| `open_reader` (three `persistence_sqlite` modules) | `ReaderOpener` | `(path, /)` |
| `function` (`variants.create_memoized_function`) | `SqlFunction`, gradual | `(*arguments, **keywords)` |
| `under_cwd` (the crawler's and `vex_checks`' command lines) | `CwdResolver`; the crawler's takes `str \| PurePath` | `(path, /)` |
| `_make_nav_context`'s return (webui `app.py`) | `ContextProcessor`, Starlette's word | `(request, /)` |
| `loops` (`CrawlerLifecycle`, `CrawlerComposition`) | `NodeLoop`, declared in the lifecycle | `(node_id, /)` |
| `loops` (`LoopSupervisor`) | `SupervisedLoop` | `()` |
| `arm_shutdown_bound` | `ShutdownBoundArmer` | `()` |
| `READERS_BY_ATTR` (matching's `matchers.py`) | `AttributeExtractor` (`Reader` names ports over our state) | `(candidate, /)` |

## Appendix B. Design notes for the teammates

### The zones (D13)

Block 10 writes, per zone, one `PLR0917` per-file ignore in `pyproject.toml` and one `ignores:` entry in the
dataclass rule, as globs. A zone is where a definition lives: its block converts the definitions and dataclasses in
it, rewrites their callers wherever they are (mypy reports each: `Too many positional arguments`), and deletes the
zone's two exclusions.

| Zone | Holds | Block |
|---|---|---|
| M1 | `catalog_matching`, `template_checks`, `coverage_checks`: `src` and `tests` | 70 |
| M2 | `p2pwatch_amule`, `amule_bump`: `src` and `tests` | 80 |
| M3 | `vex_checks`: `src` and `tests` | 90 |
| C1a | the crawler's `src/p2pwatch/domain`, its signatures (`PLR0917` only) | 100 |
| C1b | the crawler's `src/p2pwatch/domain`, its dataclasses (the dataclass rule only) | 110 |
| C2 | the crawler's `src/p2pwatch/application` | 120 |
| C3 | the crawler's `src/p2pwatch/adapters/driven/persistence_sqlite` | 130 |
| C4 | the crawler's other `adapters/driven`, `adapters/driving` and `composition` | 140 |
| C5 | the crawler's `tests/fakes`, `tests/support`, `tests/contracts`, `tests/integration`, `tests/*.py` | 150 |
| C6 | the crawler's test modules and conftests under `tests/adapters` | 160 |
| C7 | the crawler's test modules and conftests under `tests/application`, `tests/domain`, `tests/composition` | 170 |

### The mechanical recipe (blocks 70 to 170)

- A `*` right after the first parameter (after `self` or `cls` and one more); first, in a test function or fixture.
- `kw_only=True` first in the dataclass decorator's arguments; a positional class pattern (`case X(a, b)`) becomes a
  keyword pattern in its dataclass's block, which mypy reports (`Too many positional patterns for class pattern`).
- Each caller mypy reports rewritten by keyword.
- Anything else is a defect class 2 question, not a hand fix.

### Block 10

- `pyproject.toml`: `PLR0917` selected, `max-positional-args = 1`, the zones' ignores; `TID251` bans
  `typing.override` and `typing_extensions.override` (D4).
- The new rule `ast-grep/rules/dataclass-kw-only.yml` over `src` and `tests`, its tests in `ast-grep/tests/`, its
  zones in `ignores:`.
- D3's `noqa`s, written before their zone is converted (ruff does not select `RUF100`, so a `noqa` on an excluded
  line fails nothing). The callers a library makes by position, which the teammate checks against the tree:
  - the SQL functions `persistence_sqlite/variants.py` registers with `create_function`, those taking two
    arguments or more; mypy cannot see these calls (typeshed types `create_function` with `Callable[..., Any]`);
  - the row factory `_build_named_row(cursor, row)`, set on sqlite3 connections by the opener;
  - the webui's `_add_security_headers(request, call_next)`, Starlette's `dispatch=` middleware;
  - `test_app.py`'s `_TemplateRecorder.__call__(scope, receive, send)`, an ASGI app;
  - `FakeAmuleApiServer._serve_http(self, scope, receive, send)`, the ASGI app uvicorn calls; mypy cannot see the
    call either (`uvicorn.Config` takes `Callable[..., Any]`);
  - the two sqlite3 authorizer callbacks `record(action, table, *_)` of the catalog readers' tests.

  A library call mypy cannot see still runs in the unit tests, which run every line, so a missed one fails the gate.
- `test_search_task_runner.py`'s `run_for(self, seconds, client, keywords, *beside)` rewritten by hand: its
  `*beside` leaves no room for a `*`.

### Callback `Protocol`s (blocks 20 to 40)

- A `Protocol` lives in the module that receives it, `__call__` its only member, body `...`. Modules of one tach
  module share one declaration (`ReaderOpener` across `persistence_sqlite`); each adapter declares its own,
  listing exactly the keywords it passes, so mypy checks them.
- One parameter: positional-only (`/`), else mypy requires the passed function to name its parameter alike, and
  `grp.getgrnam` or a lambda would not fit.
- A callable of any signature (`SqlFunction`): `__call__(self, *arguments: Any, **keywords: Any)`, which mypy
  treats like `Callable[..., X]`.
- A callable returning a coroutine declares `async def __call__` (operator, 2026-10-30).
- A type a library already names stays: `starlette.types.Receive` and `Send`.
- A test's unbound method (`Callable[[FilesystemConfigChecker, PurePath], None]`): the instance positional-only, the
  rest by keyword, which an unbound method `(self, path)` fits.
- A double keeps its name (`FakeCommandRunner`) and fits its `Protocol` structurally.
- vulture (D10): `vulture_whitelist.py` gains `_.__call__` and a line per parameter vulture reports, each with its
  reason.
- Criterion 6: each adapter test that receives a `CommandRunner` calls it through its double with `text=False` under
  `# type: ignore[arg-type]`; strict mode's `warn_unused_ignores` fails the gate if the `Protocol` ever accepts it.

### Clock `noqa`s (block 50)

- The per-file ignores of `TID251` go: `"**/tests/**"` and the three clock adapters'.
- Each clock use gets a bare `# noqa: TID251`. A double whose docstring does not say why it reads the clock gains
  one sentence; a `FakeHanging…` double says it by its name and docstring.

### The bans (block 60)

`TID251` bans `typing.Callable`, `typing_extensions.Callable`, `collections.abc.Callable`, `typing.NamedTuple`,
`typing_extensions.NamedTuple` and `collections.namedtuple` (`typing_extensions` is installed, so its spelling would
pass otherwise). `engine.py`'s `_RuleHit` and the integration conftest's `ApiEndpoint` become frozen, keyword-only
dataclasses.

### Contract ports (block 175)

Each of the 9 pair contracts (`packages/*/tests/contracts/application/ports/driven/*_store_contract.py`) replaces
its `<Thing>Store` `Protocol` by a frozen, keyword-only dataclass `<Thing>Ports` in the contract's module, with
fields `writer` and `reader` typed by the two ports; the contract's abstract fixture returns it and its tests call
`ports.writer.<method>(...)` or `ports.reader.<method>(...)`. Each `Test<Implementation>` subclass keeps its
concrete fixture, which its own tests use, and adds a `<thing>_ports` fixture building
`<Thing>Ports(writer=store, reader=store)`. `AGENTS.md`'s rule "A pair's contract types its fixture with a
`Protocol` of the pair, named `<Thing>Store`" becomes "receives a `<Thing>Ports` of its two ports", and
`docs/contributing/testing.md`'s sentence follows (in French, as all of `docs/`).

### `AGENTS.md`, block by block

- Block 10, Hard rules: "**Keyword-only calls**: a signature takes at most one positional parameter, `self` and `cls`
  aside (`PLR0917`, `@override` banned); a dataclass is `kw_only=True` (`code-pattern-check`). A signature a library
  calls by position keeps `# noqa: PLR0917`." Also ruff's selection.
- Block 20: "a callable parameter is a callback `Protocol`, named after what one instance is"; the parameter a test
  replaces and `run_command` typed by `Protocol`s, "mypy cannot check" gone; Naming's `Protocol` rule admits a class
  whose only member is `__call__`.
- Block 50: the `TID251` paragraph: no file exempt, each clock use keeps a bare `# noqa: TID251`.
- Block 60: `Callable` and `NamedTuple` banned.
- Blocks 130 and 140: the examples `open(path, scripts)` and `AmuleApiClient(host, port, ...)` written with keywords.

### Templates

No Jinja template calls a method with two arguments, so mypy's blindness to templates hides no caller.

## Appendix C. Acceptance, as commands

1. `pyproject.toml`'s `select` holds `PLR0917` and `max-positional-args = 1`, with no per-file ignore of it; a probe
   holding `def f(a, b)` fails `uv run ruff check <probe>` with no `--select` (watched in block 10); `uv run poe lint`
   passes; `git grep -n "noqa: PLR0917"` prints only block 10's list.
2. The dataclass rule's tests refuse `@dataclass`, `@dataclass(frozen=True)` and `@dataclass(kw_only=False)` and admit
   `@dataclass(frozen=True, kw_only=True)`, watched failing first; the rule holds no `ignores:`;
   `uv run poe code-pattern-check` passes.
3. `git grep -nE "import .*\b(Callable|NamedTuple|namedtuple|override)\b|(typing|typing_extensions|abc)\.(Callable|NamedTuple|override)|collections\.namedtuple" packages`
   prints nothing; `pyproject.toml` bans the eight names of blocks 10 and 60.
4. `no-protocol-base`'s tests admit a class whose only member is `__call__` and refuse a port written as a `Protocol`.
5. `pyproject.toml` holds no per-file ignore of `TID251`; `uv run ruff check packages --select TID251,RUF100 --config
   <banned-api holding only the clock names>` passes (`RUF100` reports a `noqa` that silences nothing).
6. `AGENTS.md` no longer says mypy cannot check `text=True`; appendix B's `# type: ignore[arg-type]` test stands for
   each `CommandRunner`.

## Appendix D. Facts

On the tree at `f1b20c66` (2026-10-29), ruff 0.16.9, vulture 2.16, mypy under the root's `[tool.mypy]`
(`strict = true`).

- `uv run ruff check packages/*/src --select PLR0917 --config "lint.pylint.max-positional-args=1"`: 241 definitions;
  on `packages/*/tests`, 486: 264 test functions, 1 fixture, 128 helpers of test modules, 93 in `tests/fakes`,
  `tests/support` and `tests/contracts`. `PLR0917` is stable: no `--preview` needed.
- `PLR0917` on a probe: `def m(self, a)`, `classmethod c(cls, a)`, `def f(a)`, `def g(a, /)`, `def h(*args)` and a
  two-parameter lambda pass; `def n(self, a, b)` is flagged. Its documentation exempts `@typing.override` methods.
  `git grep -l "@override" packages`: none.
- pytest with a keyword-only fixture and test function (`def a(*, tmp_path)`, `def test_x(*, a, tmp_path)`): passed;
  `kwonly-spec-review` also passed `parametrize`, async fixtures and tests, and a contract ABC taking `self, *, ...`.
- Dataclass decorators: 192 `@dataclass(frozen=True)`, 2 `@dataclass`, 1 `@dataclass(frozen=True, order=True)`; none
  `kw_only`. `NamedTuple`s: 2, neither unpacked nor indexed. Positional class patterns: 8, in `coverage_checks`'
  command line and `vex_checks`' `image_premises.py`; mypy on a `kw_only=True` dataclass matched `case A(x)`:
  `Too many positional patterns for class pattern [misc]`.
- `Callable[` annotations: 29 lines in `src`, 26 in 17 files of `tests` (9 of them `Callable[[], X]`).
- mypy on callback `Protocol`s: `subprocess.run` passes for `__call__(self, args: list[str], /, *, check: bool,
  capture_output: bool, text: Literal[True])`, which then refuses a call without `text` (`Missing named argument
  "text"`) and with `text=False` (`incompatible type "Literal[False]"; expected "Literal[True]"`); `os.chown` passes
  for `__call__(self, *, path: Path, uid: int, gid: int)`; lambdas, `grp.getgrnam` and `pwd.getpwnam` pass for a
  `(name, /)` one. A `Protocol` with `*arguments: Any, **keywords: Any` accepts `def two(first: str, second: int)`;
  one with `*arguments: object` refuses it.
- `TID251` flags every spelling of a banned name: `from … import`, an aliased import, `collections.abc.Callable[...]`,
  `typing.Callable[...]`, `collections.namedtuple(...)`, a `typing.NamedTuple` base (8 of 8 on a probe).
- ruff has no banned list by file (`ruff config lint.flake8-tidy-imports`: `banned-api`, `extend-banned-api`,
  `banned-module-level-imports`); a nested `ruff.toml` with `extend` would replace `banned-api` for its directory
  (probe), the road D11 does not take.
- Clock uses in tests: `uv run ruff check packages/*/tests --select TID251 --config 'lint.per-file-ignores = {}'`:
  46 lines in 19 files.
- The dataclass rule's shape (a `decorator` holding `dataclass` or `dataclasses.dataclass`, bare or called without
  `kw_only=True`) flags `@dataclass`, `@dataclass(frozen=True)`, `@dataclasses.dataclass(frozen=True)` and
  `@dataclass(kw_only=False)` and admits `@dataclass(frozen=True, kw_only=True)`, one line or several (probes).
- vulture with the gate's sources and whitelist, on a probe of appendix A's shapes: `unused function '__call__'`
  (60 %) per `Protocol`, `unused variable` (100 %) for a parameter no other line reads (`capture_output`,
  `arguments`); a whitelist line `_.__call__` clears every `__call__` report.
- Library callers by position: mypy flagged each when given a `*`, but the SQL functions and `_serve_http`, whose
  library parameter is `Callable[..., Any]`; `kwonly-spec-review` searched the library calls that take our callables
  (`create_function`, `row_factory`, `set_authorizer`, `dispatch=`, `ASGITransport`, `uvicorn.Config`, `Route`,
  `Thread(target=)`, `to_thread` and more) and found no other.
- Sizes, by `kwonly-estimates` in a scratch worktree (signatures edited by an AST script, `kw_only=True` added to
  every decorator, mypy run per package): 724 definitions take a `*` (3 cannot: the two authorizer callbacks and
  `run_for`), 2254 call lines rejected; 195 decorators, 1155 constructions and 8 class patterns rejected.
  Declarations alone: 949 changed lines in 314 files; with callers, 437 files and about 5000 lines, the call sites
  estimated from mypy's errors (a multi-line call reported at its first line, so 10 to 20 % either way).
