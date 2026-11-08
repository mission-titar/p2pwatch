# Handoff: v5 lot 3, configuration validation (tier Spec)

Drafted by block 130's teammate from the block reports, corrected by the closing block, cut in two parts (140
and 142). Spec: `agents/specs/2026-11-07-v5-config-validation.md`, lot 3 of
`agents/specs/2026-11-04-v5-release-readiness.md` (the umbrella), whose D10 and D11 it implements.

## Current state

- **The matching engine is a folder of p2pwatch's domain** (D1): `p2pwatch/domain/matching/`, inside the domain's one
  tach module; `ed2k_link.py` at the domain's root. The `catalog_matching` package is gone, the workspace holds seven
  packages, and no member depends on another (`test_workspace_dependencies.py`). Its 377 tests and the golden corpus
  run in the crawler's suite. `deploy/matcher.yml`'s bytes changed (two comments, the header reflowed), so a node
  running the shipped file reevaluates its catalog once after upgrading.
- **Every problem of the three files is listed in one run** (D3): `ConfigProblem` (file, key or none, message) is a
  domain value; the driven port `ConfigChecker` returns each file's problems; `validate-config` prints one
  `Invalid config: <file>: <key>: <message>` line per problem, and the start one
  `Invalid config, refusing to start: ...` line per problem, exit 1. A file that cannot be read (absent, not UTF-8,
  not YAML) is one problem with no key, beside the other files' problems. `InvalidConfigError` carries a non-empty
  tuple of problems. Every unset `${NAME}` is listed, the reference left as written so the parse still runs; the
  refusal its key's type would add beside it is dropped, since setting the variable fixes both. 4.1.0's shipped
  files give exactly their 14 problems, to `validate-config` and to the start (`tests/fixtures/v4.1.0/`,
  `tests/support/adapters/driven/config/shipped_4_1_0.py`).
- **pydantic reads the three files, in the config adapter alone** (D2): `crawler_config_schema.py`,
  `targets_schema.py`, `matcher_config_schema.py`, and the translator `validation_problems.py`, which turns a
  `ValidationError` into problems. The messages are pydantic's ("Input should be a valid number"). In
  `crawler.yml`, the one file a `${NAME}` resolves into, none prints the value received (D7, as the operator scoped
  it on 2026-11-08); `matcher.yml`'s name the tokens and placeholders the operator wrote and give `re`'s reason. No
  error chains pydantic's, whose text holds the values. Every schema extends `StrictSchema` (`extra="forbid"`,
  `strict=True`, `allow_inf_nan=False`) and its name ends in `Schema`; the crawler's sections hold their refusing
  keys through `GetPydanticSchema`, as the matcher's tokens do. The ast-grep rule `config-adapter-pydantic` refuses
  pydantic anywhere else. The domain keeps its dataclasses and the rules across values; its parses
  (`parse_crawler_config`, `parse_download`, `parse_targets`, `parse_matcher_config`, `parse_rule`,
  `parse_condition`) and the exceptions `ConfigValueError`, `MatchingConfigError`, `UnknownTokenError`, `CycleError`
  and `DepthExceededError` are deleted. `BrokenInputError` carries its reason alone.
- **One key-path grammar**: the domain's `key_path` builds every problem's key (`search.keywords[0]`), a character
  a terminal would not print escaped wherever the key comes from: the loader, the interpolation, the translator and
  the rules across values. The translator walks the document, so a mapping key that is no string reads `tokens.1`,
  its own refusal `Key should be a valid string`.
- **A key nothing reads is refused** in every file and section (D4), a disabled `download` section included. **Every
  key 4.x used is refused in the shape**, each with what to do: `was removed, delete it from crawler.yml`,
  `moved to 'search.backoff', move it in crawler.yml`, `was renamed 'audience', rename it in crawler.yml`. A moved or
  renamed key is one problem: pydantic's "Field required" for its new place is dropped. `webui.host` and `webui.port`,
  ignored on purpose until now, are refused as removed.
- **Values are strict** (D6): no conversion (`"5"`, `true` for a number, `2.7` for an episode, a numeric title are
  refused), `.inf` and `.nan` refused, today's bounds kept. `download` is a tagged union on `enabled`: its wiring is
  required only when on, every key present typed either way, a null `poll_interval_seconds` included.
  `TargetSegment.status` is typed by its closed set, `TargetStatus`. A matcher token is a tagged union over its
  shape, chosen by a discriminator that never raises; a token or rule of no shape or of two gets a refusing tag.
  Conditions are recursive through a PEP 695 alias and `GetPydanticSchema`.
- **The rules across values run once their file's shape holds** (D3), each returning every problem at its key:
  `crawler.yml`'s backoff cap below its base (`cross_value_problems`); `targets.yml`'s duplicate `target_id`s
  (`duplicate_targets`, letters compared upper-cased, each naming its first holder); `matcher.yml`'s
  `cross_value_problems`: its fragments, unknown references, a duplicate veto, an override on a token that is not a
  coverage one, each cycle, the depth bound only when no cycle, then each regex that cites an unknown placeholder or
  does not compile, which a fragment problem leaves unchecked since the regexes hold the fragments. The graph walk
  keeps its own stack: a chain of 5000 tokens is a depth problem, not a `RecursionError`.
- **A key written twice in one mapping is refused** (D5): `load_yaml` returns a `LoadedDocument` (the document and
  these problems), `<key path>: written twice, at lines A and B` (`written twice on line A` for a flow mapping). The
  document keeps the latest value, which its schema still checks. A merge key's override is not a duplicate; an alias
  is checked once, at its anchor.

## What was built, block by block

| # | PR | Block | Lines, files |
|---|---|---|---|
| 10 | #661 | the matching engine folded into p2pwatch's domain (mechanical, waiver) | 511, 136 |
| 20 | #662 | `validate-config` checks every file and lists their problems | 258, 17 |
| 30 | #664 | the start refuses with every problem of the three files | 414, 14 |
| 40 | #665 | each section of `crawler.yml` parsed on its own (refactor) | 175, 2 |
| 42 | #666 | pydantic, its confinement, the translator; `crawler.yml`'s root refuses every key nothing reads | 372, 12 |
| 44 | #667 | `crawler.yml`'s root values by pydantic | 340, 6 |
| 46 | #668 | `search` by pydantic, the backoff rule across values, a moved key one problem | 352, 7 |
| 50 | #670 | `webui` by pydantic | 155, 4 |
| 52 | #671 | `observability` and its notifications by pydantic, `renamed_key` | 497, 8 |
| 60 | #673 | `download` by pydantic, on or off, the tag mark | 244, 5 |
| 62 | #674 | `download` built from its schema, the domain's last `crawler.yml` parse deleted | 414, 5 |
| 70 | #676 | `targets.yml` read through `targets_from_document` (refactor) | 123, 12 |
| 80 | #677 | `targets.yml`'s values by pydantic | 254, 5 |
| 82 | #678 | the targets built by the adapter, every duplicate listed | 355, 8 |
| 90 | #680 | `matcher.yml` read through `matcher_config_from_document` (refactor) | 122, 12 |
| 100 | #681 | the fragments and leaf tokens by pydantic, the 4.x names | 428, 6 |
| 102 | #682 | the rule and condition parses public, the graph tests built from the domain (refactor) | 310, 2 |
| 104 | #683 | the tokens built by the adapter, every fragment problem listed | 455, 5 |
| 110 | #685 | the rules by pydantic | 424, 10 |
| 112 | #686 | the conditions by pydantic, the domain's structural parse deleted | 453, 5 |
| 120 | #688 | the matcher's problems across values all listed, the graph's exceptions deleted | 463, 6 |
| 130 | #689 | a key written twice refused, both lines named | 254, 6 |
| 140 | | one strict base for every schema, the crawler's sections through `GetPydanticSchema`, the null poll interval, no chained pydantic error; the contributing pages and the matching rule; 4.1.0's fixtures and their test | 359, 18 |
| 142 | | `matcher.yml`'s messages named, a fragment problem hiding the regexes alone; one key-path grammar, an unset variable one problem, `BrokenInputError(reason)`; the records | 377, 19 |

Twenty-two blocks plus the closing one, cut in two (140, 142): 24, the spec's 14 rows plus 10 from the splits. The
operator accepted a stack past the workflow's 19 on 2026-11-07 (the spec's section 5, up to 21), then up to about 24
on 2026-11-08.

- **Seven splits, each for a bound**:
  - Block 40 (about 890 lines with its refactor) into four: 40 the section parses made public, 42 the root's unknown
    keys with pydantic's arrival, 44 the root's values, 46 `search`.
  - Block 50 (636) into 50 `webui` and 52 `observability`.
  - Block 60 (643, 8 files) into 60 the schema and 62 the build and deletions.
  - Block 80 (576, 10 files) into 80 the schema and 82 the build, the duplicate rule and deletions.
  - Block 100 (1148, 9 files) into three: 100 the schema, 102 the parses made public and the tests rerouted, 104 the
    build and deletions.
  - Block 110 (811, 10 files) into 110 the rules and 112 the conditions.
  - The closing block (733 lines, 32 files) into two, the records last: 140 the schemas, the pages and the
    fixtures, 142 the matcher's checks, the key paths and the records; the key paths' 17 files and the matcher's
    share three, which set the cut.
- **Why each split runs where it does**: `dead-code-check` (vulture) refuses a schema field nothing reads and a
  function nothing calls, and `_unit-coverage-check` refuses a module that loses its own tests. So a part that writes
  a schema still hands its checked values to the domain's parse key by key (60, 80, 100), and the part that deletes a
  parse deletes or reroutes its tests in the same commit (62, 82, 104, 112).
- Departures, per block (the spec's `(Corrected: ...)` marks are the closing block's):
  - Block 10: `tach.toml`'s `ports.driven.coverage_reader` gains `depends_on = ["p2pwatch.domain"]` (an import of
    `DecisionTier` and `TargetId` across distributions, which tach never saw); the root `pyproject.toml`'s ruff `src`,
    isort `known-first-party` and vulture `paths` drop the package; the golden corpus's `tests_without_unit` entry
    moves; `tests/application/conftest.py` finds the golden targets from its own path; `.claude/CLAUDE.md`'s
    path-scoped table names `matching.md`'s paths in words. 511 lines, over the estimate (330 to 450), mostly the
    deleted `packages/matching/pyproject.toml`.
  - Block 20: `BrokenInputError(path, *, reason)`, its `str` unchanged, so a broken file's line names the file once;
    `ConfigProblem` moved in a commit of its own; `tach.toml`'s two config ports depend on `p2pwatch.domain`.
  - Block 30: `ConfigValueError(key, *, message)` keeps the old class's signature (renamed in its own commit); the
    parse runs on the document even with a variable unset, the reference left as written; `interpolate_document` takes
    the file's path and returns `InterpolatedDocument(document, problems)`; the callback `Protocol` `FileRead`, generic,
    moved to `crawler_config.py`. 414 lines against an estimate of about 250.
  - Block 42: the schema is built with `create_model` from key lists, since vulture reports a refusing field as an
    unused variable; config given as class keywords or `__config__` for the same reason. The tagged union's tag
    dropping waited for block 60.
  - Block 44: `parse_crawler_config` deleted here, not in block 60 (nothing in `src` called it once the adapter built
    the config); a section that is no mapping is refused by the root schema, its domain parse not run.
  - Block 46: the backoff rule's message names no value (`should be at least base_seconds`, where 4.x printed both
    numbers); the rule is `cross_value_problems(config, *, file_path)`, returning problems.
  - Block 50: none; `webui.host` and `webui.port` refused as removed, as the spec asks.
  - Block 52: `moved_key` and `renamed_key` share one refusal (`config_key_replaced`); `DEFAULT_LOG_LEVEL` is
    `Final`, since mypy refuses a `str` default for a `Literal` field.
  - Block 60: the translator's tag mark (`~`) arrives here, `download` being the first tagged union; "the wiring
    required only when on" is a tagged union on `enabled`, not a validator, which would wait for every other key.
  - Block 62: `ConfigValueError` deleted here, not in block 110 as block 30's design says: its last user was the
    download parse.
  - Block 70: `targets_from_document` lives in `targets_schema.py`, the module block 80 fills; file-reading call sites
    use `read_targets(path)`, so the golden corpus loads `golden_targets.yaml` through `load_yaml`. 123 lines, 12 files
    (estimate 70 to 100, 10): the new module and its own tests.
  - Block 80: the closed status set is `TargetStatus`, a `Literal` in the domain's `models.py`; `LOST` is `Final`.
  - Block 82: `duplicate_targets` returns `TargetDuplicate(index, first_index)`, so the adapter names both places
    without printing an id; a `kw_only` dataclass, the gate banning `NamedTuple`.
  - Block 90: none beyond block 70's; in-memory call sites pass `PurePath("matcher.yml")`.
  - Block 100: `vetoes` typed `list[str]` here, not in block 110; the refusing tag is a `dict[str, Any]` type with a
    `BeforeValidator`, not a model; a non-mapping token's discriminator returns `None` with a static error;
    `{segment}` also refused in a fragment's text; `attr_between` a `Literal` held equal to `READERS_BY_ATTR` by
    tests; `DEFAULT_REGEX_FLAGS` and `DEFAULT_MIN_SIMILARITY` join `domain/matching/config.py`; the renamed-attribute
    message names the 4.x attribute, the empty range reads `'min' is above 'max', an empty range`.
  - Block 102: none.
  - Block 104: `fragment_problems` returns every fragment problem under `fragments.<name>`, where the old checks raised
    on the first.
  - Block 110: `Scope` (a PEP 695 `Literal` alias) joins `domain/matching/config.py`, `SCOPES` leaves; no condition
    and two conditions both read `exactly one condition (all/any/not) expected, got [...]` (4.x's message for none
    named the rule, a value); `refuse_control_character` moves to `validation_problems.py`, used by `targets_schema.py`.
  - Block 112: `GetPydanticSchema` replaces block 100's `create_model` and `GenericAlias` on the tokens field; a
    refusing tag is typed `Any`; an operand neither string nor mapping reads our
    `Input should be a valid string or dictionary`; a leaf key beside a condition key is now refused, closing block
    100's departure.
  - Block 120: the function is `cross_value_problems`, not `validate_config` (the use case's method's name); keys
    follow pydantic's locations, by index; D7 read strictly (an unknown reference, an unknown placeholder and a regex
    that does not compile name no value, `re`'s reason dropped); one problem per override field; each citation
    closing a cycle listed, two cycles sharing a token possibly as one; the depth problem one, at the deepest token.
  - Block 130: the `SafeLoader` subclass walks the composed node tree in `construct_document`, since the constructor
    builds nested values lazily and knows no key path; a key written three times gives two problems, each naming the
    first line; these problems come before the file's interpolation and schema problems; a merge key's own mapping is
    checked, at the merging mapping's path; the three reads share `_parsed(problems, parse=...)`.
  - Blocks 140 and 142: the base class is `StrictSchema`, public in `validation_problems.py` since three modules
    extend it (the review suggested a private `_Schema`); a base whose refusing keys a built schema adds is
    `_<X>KeysSchema`, and the type aliases end in `Schema` too (`_TokenSchema`, `_RuleSchema`); `cross_value_problems`
    takes the fragments and calls `fragment_problems` itself, so no caller sequences the two; an unknown placeholder
    is found by `PLACEHOLDER` against `TARGET_PLACEHOLDERS`, one problem per placeholder (`main` gave the first);
    the matcher's token and fragment names are escaped too, through `key_path`; the 4.1.0 test reads `targets.yml`
    from `deploy/`, byte-identical to 4.1.0's, since its 598 lines would pass the line bound alone. Class 1:
    `TargetStatus` typing showed the download cycle's support target `063A` holding `complete`, a status no
    `targets.yml` can give; it holds `found`, and `test_complete_target_candidate_is_skipped`, which tested that
    impossible target, is deleted (the unknown target's test keeps the `complete` path).
- **Behaviour found** (block 112): a condition nested inline past about 100 levels is refused,
  `Recursion error - maximum validation depth exceeded` (pydantic's bound); on `main`, 200 levels were accepted and
  1000 crashed the parse with a `RecursionError`.

## The holistic review's findings and their exits

`.reviews/v5-lot3-holistic.md`: 1 MAJOR, 15 MINOR, no CRITICAL. Every exit was settled by the lead and the operator on
2026-11-08.

| # | Finding | Exit |
|---|---|---|
| 1 | MAJOR: appendix B's rows 1 and 2 met by probes only, no test keeping 4.1.0's 14 problems (the draft of this handoff assumed one) | fixed, block 140: 4.1.0's `crawler.yml` (notifications uncommented) and `matcher.yml` as fixtures, `targets.yml` from `deploy/`; one command-line test, for `validate-config` and for the start, asserts the 14 `<file>: <key>: <message>` lines in order and exit 1 |
| 2 | latent secret leak: `from error` chains pydantic's error, whose text holds the resolved `${NAME}` | fixed, block 140: `from None` at the three sites; block 142: a traceback of the start's error holds no resolved variable |
| 3 | D7 read strictly in `matcher.yml`, unevenly | fixed, block 142: the operator's option (a), D7 scoped to `crawler.yml` and marked; the unknown token, the unknown placeholder and `re`'s reason named again |
| 4 | an unset `${NAME}` is two problems at one key | fixed, block 142: a parse problem at an unresolved variable's key is dropped |
| 5 | a fragment problem hides the whole graph | fixed, block 142: only the regexes wait |
| 6 | the crawler's schema re-declares its sections with `create_model` and `GenericAlias` | fixed, block 140: `GetPydanticSchema`, as the matcher's |
| 7 | `BrokenInputError`'s `path` feeds an unused `str` | fixed, block 142: `BrokenInputError(reason)`, its test the reason alone |
| 8 | the `(?i)` branch and its non-discriminating test | fixed, block 142: both deleted |
| 9 | `docs/contributing/architecture.md`'s three stale passages | fixed, block 140 |
| 10 | `.claude/rules/matching.md`'s "both packages" and its `paths` | fixed, block 140, with `.claude/CLAUDE.md`'s table row |
| 11 | the stale test comment | fixed, block 142 |
| 12 | `tokens[1].[key]`, and key paths escaped in one place of four | fixed, block 142: `key_path`, the document walked, `tokens.1: Key should be a valid string` |
| 13 | a download off accepts `poll_interval_seconds: null` | fixed, block 140 |
| 14 | nothing guards strictness on a new schema | fixed, block 140: `StrictSchema` |
| 15 | `TargetSegment.status` a `str` beside `TargetStatus` | fixed, block 140 (a class 1 fix with it, above) |
| 16 | schema names in three patterns | fixed, block 140: every one ends in `Schema` |
| 17 | the compose smoke test's flake, outside the lot | fixed after the lot, tier Direct: `_wait_new_shared_hash` bounded by a 180 s deadline, its failure naming the last reading, `ed2k`'s state and health, and its logs |
| marks | the spec's departures not marked | fixed, block 142: every mark of the review's table, D7's as the operator decided, appendix B row 1's for `targets.yml` |

Each new behaviour's test, watched failing (or proven by a mutation where it passed at once):

| Test | Failure |
|---|---|
| `test_a_download_value_out_of_its_type_is_refused_whether_on_or_off[...None...-off]` | `Failed: DID NOT RAISE InvalidConfigError` |
| `test_the_error_chains_no_pydantic_error_which_holds_the_values` (three schemas) | `AssertionError: assert 1 validation error for CrawlerConfigSchema ... is None` (and `TargetsSchema`, `MatcherConfigSchema`) |
| the matcher's named messages (domain and adapter) | `('tokens.t.any[1]', 'references an unknown token') != ('tokens.t.any[1]', "references the unknown token 'ghost'")` |
| `test_a_fragment_problem_hides_the_regex_checks_alone` | `Right contains one more item: ('tokens.t.any[0]', "references the unknown token 'ghost'")`; the regex skip mutated away, it and its domain twin fail |
| `test_an_unset_variable_is_one_problem_its_value_as_written_not_refused_beside_it` | `At index 1 diff: ('observability.log_level', "Input should be 'DEBUG', ...")` |
| `test_no_traceback_prints_a_resolved_variable` | passed once block 140 held; `from error` restored: `'hunter2' is contained here: ut_value='hunter2'` |
| the key paths escaped (interpolation, matcher names) | the key printed with the raw escape character where `un\x1bread` and `fragments.title\x1b` were expected, as text |
| `test_a_key_that_is_no_string_is_named_as_a_key_both_it_and_its_value_refused` | the walk mutated to read every integer as an index: `key='scores[1]'`; the message mutated: `'Input should be a valid string'` |
| `test_a_broken_file_carries_its_reason` | `TypeError: BrokenInputError.__init__() missing 1 required keyword-only argument: 'reason'` |
| the 4.1.0 test, for both commands | passed at once; the root's removed keys mutated to accepted: `At index 4 diff: ... 'backoff' ... != ... 'cycle_interval_seconds'` in both |

## The Wrap's measurements

By the lead on 2026-11-08 on the top before the closing block (`b99dec84`); probes and the migrated copies in the
lead's scratchpad.

| Row | Result |
|---|---|
| `validate-config` on the operator's 4.x files read in place, their `${NAME}` set | exactly the 15 problems of appendix C, exit 1 |
| The same files migrated by the 15 actions, and `deploy/`'s | `Config valid` |
| Equal domain objects: `main`'s parse (a worktree at `70e68d21`) against the lot's | byte-identical `repr`s of every config object and the same policy fingerprint, on `deploy/` and on the migrated copies |
| The compose smoke test | block 130's first amd64 run failed it once (`_wait_new_shared_hash`, `got []`), passed on rerun (run 42445160322, attempt 2) |
| pydantic's resident memory in the image | not measured: the reviewer measured about 14 MB on the host; the umbrella's release candidate row checks the image |

The closing block changed none of the 15 problems' messages. Its teammate re-ran the `repr` probe on `deploy/` between
`b99dec84` and the top of block 142: identical, fingerprint included.

## Accepted limits

The spec's section 6, plus:

- **A condition nested inline past about 100 levels is refused** by pydantic's validation depth (block 112), with
  pydantic's message; tokens, which cite one another by name, have the engine's own bound of 32.
- **A key that is no scalar** (`? [a]`) is refused as invalid YAML by PyYAML, not as a key written twice (block 130).

## For lot 7 (the operator pages, umbrella D19)

The spec's section 6 lists what the pages must say; the blocks found these stale passages:

- `docs/migration-4x.md:80` quotes `token 'title_hit': key 'min' was renamed 'min_coverage', rename it in matcher.yml`;
  it now reads `tokens.title_hit.min: was renamed 'min_coverage', rename it in matcher.yml` (block 100).
- `docs/migration-4x.md:233` quotes `segment letter 'a\x1fb' holds a control character`; it now reads
  `episodes[0].segments[0].letter: holds a control character`, without the value (block 82).
- New messages no page quotes yet: `written twice, at lines A and B` and `written twice on line A` (block 130); the
  backoff rule's `should be at least base_seconds` (block 46); the graph's messages (block 120's table).
- No page quotes a rule, condition or graph message (`git grep` on `docs/`, blocks 110, 112, 120). Since block 142
  they read `references the unknown token 'x'`, `cites the placeholder '{x}', neither a fragment nor a target field`
  and `does not compile as a regex: <re's reason>`; a mapping key that is no string, `Key should be a valid string`
  (block 142).

## The lot's counts

- Fix-backs: 0. Cascaded rebases: 0. Runs re-triggered by them: 0. One run re-run for the flake (block 130,
  42445160322, attempt 2).
- Rebases onto `main`: none so far: `main` has not moved during the lot (still `70e68d21`, the merge base of block
  10's branch).
- Splits: 7 (40 in four, 50, 60, 80, 110 and the closing block in two, 100 in three). Class 2 questions: 0. Class
  1 fixes: 3 (block 10, `webui/format.py`'s docstring calling `ed2k_link` a package; block 82,
  `tests/smoke/targets.yml`'s comment naming `parse_targets`; block 140, the impossible `complete` target above).
- Bodies the operator called unreadable: none.
- Block 40's first report claimed continuous integration green while its runs were still in progress.

## Pitfalls learned

- **Serena's index stayed stale from block 60 on** (`find_referencing_symbols` returned nothing on recent names, and
  `safe_delete_symbol` listed references already gone after `sed` or `poe fix` edits): every block after it found
  usages with `git grep -n -w` and checked each edit with `git diff --word-diff`. A Serena rename in block 30 also
  reached a dated instrument under `agents/reference/`, reverted.
- **vulture reports a pydantic field nothing reads**, every refusing field included, and a `model_config`, a
  `model_validator` method, a model class nothing names: schemas are built with `create_model` from key lists or with
  `GetPydanticSchema`, config as class keywords, the empty range as an `AfterValidator`.
- **`_unit-coverage-check` credits a body run at import to no test**: a type built at module level by a helper
  (`removed_key(...)`) needs its module's own tests to build it, or a module-level comprehension; a
  `GetPydanticSchema` lambda is written at module level, not returned by a function. A new attribute on a domain error
  needs its module's own test.
- **A discriminator that raises drops every other problem of the document**: it returns a refusing tag instead.
- **pydantic's message for a `ValueError` reads "Value error, ..."**: our refusals raise `PydanticCustomError`.
- **A length constraint after a function validator** gives the generic `Value should have at least 1 item after
  validation`: the `Field` goes before the validator.
- **mypy**: `list[X]` of a `create_model` class is refused (use `types.GenericAlias(list, X)`); a variable schema in
  `Annotated[...] | ...` needs the alias annotated `Any`; `create_model(**fields)` type-checks only with a
  `dict[str, Any]`; a `str` default for a `Literal` field needs a `Final` constant.
- **`get_args` on a PEP 695 alias is empty**: `get_args(Scope.__value__)`. A recursive condition schema is a PEP 695
  `type` written before the classes that hold it.
- **Fields of a class built from two models come in reversed MRO order**; `not`, a keyword, is a field with
  `Field(alias="not")`, and an error's location names the key.
- **A `match` whose last case names a class** leaves an exit branch no test takes: the last case is `case _`.
- **An ast-grep test file without its rule passes** (`Configuration not found!`, exit 0): watch it fail with a partial
  rule.
- **`collections.abc.Callable` is banned** (`TID251`): a callback `Protocol`, generic when its return varies. PLR0917:
  a private method takes one positional argument beyond `self`. The domain rings allow no `itertools`.
- **The Bash tool runs zsh**: an unquoted variable holding two paths is not word-split, and `env $E` does not split
  `$E` (a mutation loop and a probe broke silently on it).
- **`git mv` plus `poe fix`**: stage with `git add -A -- packages`, never a pathspec naming the deleted directory, which
  stages nothing; `uv sync` leaves the deleted package's untracked caches behind, which make `packages/*` name a member
  with no `pyproject.toml`.
- **`node_id` is a removed key of `crawler.yml`**: a test wanting a wrong value picks another.
- **PyYAML builds an alias cycle as a node cycle**: a walk of the composed nodes must remember the nodes it saw.
- **mypy reads pydantic's `Field(default=None)` on a field typed without `None` as an assignment error** (pydantic
  is a `dataclass_transform`): a key optional but never null takes a default of its type, which pydantic never
  validates.
- **`raise ... from None` leaves `__context__` set**, `__suppress_context__` true: a traceback prints neither, but a
  test of the leak renders `traceback.format_exception`, with the secret off the line of the call, which a traceback
  quotes.
- **pydantic ends a mapping key's error location with `[key]`**, after the key itself, kept as YAML read it (an
  integer for `1:`): only the document tells an index from such a key.

## Not validated

- The Wrap's rows on the operator's files ran on `b99dec84`, before the closing block; the closing block changes none
  of their 15 messages and leaves `deploy/`'s objects identical (its probe above), but was not re-run on the
  operator's files.
- The image build without `packages/matching` (block 10): run by continuous integration only.
- pydantic's resident memory in the image (D2's 14 MB, under the umbrella's 150 MB row): not measured by any block.
- No Docker suite was run locally by any block: none touched one; continuous integration runs the compose smoke test.
- `deploy/matcher.yml`'s new fingerprint triggering one reevaluation on a node running the shipped file (block 10):
  stated, not run.

## Next step

The lead rebases the stack onto `main` if it moved and waits for every run to be green; the operator reads the stack
and merges it. No release: v5 ships after lots 3 to 7 and the release candidates (`BACKLOG.md`'s "v5 release
readiness" entry, which stays, lots 4 to 7 remaining). Lot 4 next, fault isolation, per the umbrella.
