# v5 lot 3: configuration validation

Tier Spec. Discussed with the operator on 2026-11-07, as lot 3 of `agents/specs/2026-11-04-v5-release-readiness.md`
(the umbrella), whose decisions D10 and D11 this lot implements. Its finding is the umbrella's appendix A "Lot 3". The
decisions are the operator's; their reasons are those given in the discussion, the lead's included where the operator
accepted a recommendation. Every measurement was re-run on 2026-11-07 on `main` at `70e68d21` (appendix C). The
spec's commit marks the umbrella's appendix A "Lot 3" (`(Corrected: 13 in the operator's crawler.yml, lot 3's
appendix C)`) and appendix C row "Unmigrated config" (`(Corrected: the 15 problems of lot 3's appendix C)`), and the
hexagonal architecture spec's D3 (`(Corrected: folded into p2pwatch's domain, v5 lot 3's D1)`).

## 1. In short

A node's configuration is three files. Today `validate-config` and the start stop at the first problem of the first
wrong file, so an operator who carries a 4.x configuration over fixes it in fifteen runs, one refusal each. The lot
reads the three files through pydantic, the reference library for typed input in Python, which lists every problem of
a document at once; refuses the two kinds of mistake that pass today without a word, a key nothing reads and a key
written twice; and, first, folds the matching engine back into p2pwatch, the separate package having lost its reason.

## 2. What the operator will see

- **One run of `validate-config` lists every problem of the three files**, each with its file and its key; the start
  refuses with the same list. A 4.x configuration carried over shows its 15 problems at once, one per key to act on.
- **A file that cannot be read** (absent, not YAML) is one problem among the others: the other files are still checked.
- **A key nothing reads is refused**, where today it is ignored: `downlaod.enabled: true` no longer leaves downloads
  off in silence.
- **A key written twice in one file is refused**, naming both lines, where today the second wins in silence.
- **A value of the wrong type is refused everywhere**: `min_coverage: "0.6"` or an episode number `2.7` in the policy
  files, accepted and converted today, are refused like `crawler.yml`'s.
- **The messages are pydantic's** ("Input should be a valid number"), and ours where pydantic has nothing to say: a
  key removed, moved or renamed since 4.x, and the rules across values (a reference to an unknown token, a cycle, a
  backoff cap below its base).
- The operator pages (`settings.md`, `troubleshooting-start.md`, the migration guide) are lot 7's (umbrella D19):
  this lot lists what they must say (section 6).

## 3. Decisions

- **D1. The matching engine leaves its package for p2pwatch's domain, moved as it is.** *It became a package of its
  own on 2026-06-22 so that the webui, then a separate program, could share it; the consolidation of 2026-07-06 put
  both in one process, and p2pwatch is now its only user. Its tests read the real `matcher.yml`, which they could no
  longer do once the parse moves to p2pwatch's config adapter (D2).* It becomes a folder of the domain like
  `download/` or `search/`, inside the domain's one tach module: *a boundary of its own would be the only one inside
  the domain, for a reuse nobody needs any more, against no known defect* (the operator's decision of 2026-11-07).
  `ed2k_link.py` goes to the domain's root: *it builds a file's link for the amuleapi client, the notifier and the
  webui, and lived in the package only because it was the shared one.* A purely mechanical block, past the size
  bounds with the operator's waiver. Block 10.
- **D2. pydantic reads the three files, in the config adapter alone; the domain keeps its objects and the rules
  across values.** *pydantic lists every problem of a document natively and was built to be extended: our messages
  for the keys 4.x used, a tagged union for the matcher's token shapes. In the adapter, it is the boundary Cockburn
  describes (the adapter translates the outside representation, the core never sees it), and the domain stays
  testable without it.* A rule of the gate keeps pydantic out of every other module. Importing it costs the crawler
  about 14 MB resident, under the umbrella's 150 MB memory row. Blocks 40 to 110.
- **D3. Validation lists every problem in one pass: every file is checked, every value of a file is checked, and the
  rules across values run once their file's shape holds.** *D10 of the umbrella; a rule across values on a file whose
  shape fails would report the consequences of its first problem (a reference to a token whose definition failed),
  so it waits for the next run.* Every key 4.x used is refused in the shape, so a 4.x file shows all of them in one
  run. Blocks 20 to 120.
- **D4. A key nothing reads is refused, in every file and every section**, a disabled `download` section included.
  *Today such a key is ignored, so a misspelled option is silently not applied; every key of the operator's, 4.1.0's
  and `deploy/`'s files is read, or removed, moved or renamed since 4.x (appendix C), so this adds nothing to the
  upgrade.* Blocks 40 to 110.
- **D5. A key written twice in one mapping is refused**, naming its two lines. *The YAML reader keeps the last one in
  silence, which ignores a whole block; pydantic receives the document already read and cannot see it.* Block 130.
- **D6. Every value is checked strictly, with no conversion**: a number where a number is expected, a string where a
  string is. *`crawler.yml` already refuses `"5"` for a number; the policy files accept it today by converting, and
  truncate `2.7` to episode 2, a silent error of the kind D4 refuses. The operator's, 4.1.0's and `deploy/`'s policy
  files hold no value this refuses (appendix C).* Blocks 80 to 110.
- **D7. A problem's message is pydantic's; ours where pydantic says nothing.** *The operator chose pydantic's
  wording: lot 7 rewrites the pages that quote the messages, and a table translating each pydantic error type into
  today's sentence would redo by hand what the library does.* Ours: a key removed, moved or renamed since 4.x, with
  what to do, and the rules across values. A key moved or renamed is one problem: the missing new name beside it is
  not listed, since the one edit fixes both. No message prints the value received: `${NAME}` is resolved before the
  parse, so an unknown key or a type error would print a resolved password or webhook token, which `main` never
  does; the key and the expected type name the problem, and the operator has the file in hand. Blocks 40 to 120.
- **D8. No command rewrites a 4.x configuration** (umbrella D11). *D7 already names each key with its action.* No
  block.

## 4. Acceptance

Commands and tests in appendix B.

### In tests and CI

| Check | After the lot | On main |
|---|---|---|
| `validate-config` on 4.1.0's shipped files, notifications uncommented | the 14 problems of appendix C, nothing else | the first one |
| The start on the same files | refuses with the same list, exit 1 | refuses on the first one |
| A broken `targets.yml` beside a wrong `matcher.yml` | both listed | `error:` on the first, exit 1 |
| Two wrong values in one section, and a third in another section | all three listed | the first |
| `${NAME}` unset in two values | both listed | the first |
| A key nothing reads, at the root, in a section, in a disabled `download` | refused | accepted |
| A key written twice | refused, both lines named | the second wins |
| `min_coverage: "0.6"`, an episode number `2.7`, a numeric title | refused | converted |
| A float `.inf` or `.nan` | refused | refused |
| A token whose definition fails, cited by two rules | the definition's problem, no reference problem | the definition's problem |
| A valid file whose rules break two cross-value checks | both listed | the first |
| pydantic imported outside the config adapter | the gate fails | refused in the core rings only |
| The matching engine's tests, golden corpus included | green inside p2pwatch's suite | green in their own package |

### On the operator's files, at the lot's Wrap

| Check | After the lot | On main |
|---|---|---|
| `validate-config` on the 4.x `crawler.yml`, `targets.yml`, `matcher.yml` (read only) | the 15 problems of appendix C, nothing else | one |
| The same files migrated by the guide | `Config valid` | `Config valid` |
| `deploy/`'s three files | `Config valid` | `Config valid` |

### What must not change

- Every valid configuration loads into equal domain objects: `deploy/`'s files and the operator's migrated ones
  compared, `main`'s parse against the lot's (appendix B).
- The matching decisions: the golden corpus and the engine's tests, unchanged in substance by block 10.
- The policy fingerprint, which hashes the files' bytes: the existing tests.

## 5. Blocks

| # | Branch | Change | Decisions | Estimate (lines, files) |
|---|---|---|---|---|
| 10 | `refactor/fold-matching-into-p2pwatch` | the matching engine moved into p2pwatch's domain (mechanical, waiver) | D1 | 330 to 450, 135 to 140 |
| 20 | `feat/validate-config-lists-every-file` | `validate-config` checks every file and lists their problems | D3 | about 300, 12 |
| 30 | `feat/start-refuses-with-every-problem` | the start refuses with every problem, every unset variable listed | D3 | about 250, 9 |
| 40 | `feat/crawler-config-schema-root` | pydantic, its confinement, the problem lines; `crawler.yml`'s root, `search`, the root's 4.x keys | D2 to D4, D7 | 550 to 650 |
| 50 | `feat/crawler-config-schema-observability` | `observability` and `webui` by pydantic, their 4.x keys | D2 to D4, D7 | 450 to 550 |
| 60 | `feat/crawler-config-schema-download` | `download` by pydantic, the domain's parse deleted | D2 to D4, D7 | 550 to 650 |
| 70 | `refactor/targets-read-from-a-document` | the tests read `targets.yml` through the adapter | D2 | 70 to 100, 10 |
| 80 | `feat/targets-schema` | `targets.yml` by pydantic, every duplicate target listed | D2 to D4, D6, D7 | 450 to 600, 8 |
| 90 | `refactor/matcher-config-read-from-a-document` | the tests read `matcher.yml` through the adapter | D2 | 120 to 160, 10 |
| 100 | `feat/matcher-config-schema-tokens` | the fragments and the leaf tokens by pydantic, the 4.x names | D2 to D4, D6, D7 | 550 to 650, 6 |
| 110 | `feat/matcher-config-schema-rules` | the conditions, rules and vetoes by pydantic, the structural parse deleted | D2 to D4, D6, D7 | 600 to 700, 6 |
| 120 | `feat/matcher-cross-value-problems` | the matcher's rules across values, every one listed | D3, D7 | 390 to 560, 5 to 8 |
| 130 | `feat/yaml-duplicate-keys-refused` | a key written twice refused | D5 | 160 to 270, 7 to 12 |
| 140 | `docs/v5-config-validation-wrap` | closing block | | |

Estimates by a Sonnet agent (`.reviews/v5-lot3-estimate.md`) on a first cut of eight blocks, which it split into this
one; it counted every rewritten test as deleted then added. Seven rows reach the line bound on that count (40, 50,
60, 80, 100, 110, 120), each splitting once more if it passes, which would take the stack to 21 blocks. The
operator accepted on 2026-11-07 a stack past the workflow's 19 in one lot rather than two lots: each split takes a free
number, and the lead asks again only past 21.

## 6. Limits and scope

### Accepted limits

- **A rule across values waits for its file's shape** (D3): a matcher whose token definition fails shows that problem;
  the references, cycles, vetoes and regex compilation are checked at the next run, once the shape holds.
- **A file that is not YAML yields one problem**: the reader cannot go past the syntax error.

### For lot 7 (umbrella D19)

- `troubleshooting-start.md` and `troubleshooting.md`: the start's refusal is a list, one line per problem, each with
  its file; the messages are pydantic's.
- `settings.md`: an unknown key and a key written twice are refused; values are typed strictly.
- The migration guide: `validate-config` lists a 4.x configuration's every problem in one run, the step to run before
  the first start.

### Adjacent backlog items

- **Test quality** and **mutation testing in the gate**: their measurements were taken per package, matching's
  included (its pilot run); D1 folds matching's tests into the crawler's run, so those lots redo their measurements
  when they open. Both stay open: tooling debt, nothing the operator meets in the upgrade.
- **The Grype scan back on p2pwatch**: pydantic and pydantic-core enter the image it will scan and its SBOM; it stays
  after the v5.0.0 tag (umbrella D21).
- The others are another lot's or after v5 (umbrella, "Adjacent backlog items").

## Appendix A. Design, block by block

Every block is written in strict TDD (workflow, Act): each new behaviour's test is written first and watched failing,
its failure line in the block report. Every block is green alone: `dead-code-check` refuses a function whose caller
lands in a later block, so each document-reading function of blocks 70 and 90 is called by `read_targets` or
`read_matcher_config`, not by the tests alone.

New names: the schema modules `crawler_config_schema.py`, `targets_schema.py`, `matcher_config_schema.py` and the
translator `validation_problems.py` in `adapters/driven/config/`; `targets_from_document` and
`matcher_config_from_document`, the functions of blocks 70 and 90. `.claude/rules/glossary.md` gains `config problem`
(`ConfigProblem`, one problem of a config file: the file, the key or none, the message; never a refusal, an error) and
`schema` (a pydantic model of a config file as written, in the config adapter only) in block 20 and block 40.

### Block 10: the matching engine moved into p2pwatch's domain (D1)

- `packages/matching/src/catalog_matching/domain/*.py` to `packages/crawler/src/p2pwatch/domain/matching/`, by
  `git mv`, contents unchanged but their imports; `ed2k_link.py` to `packages/crawler/src/p2pwatch/domain/`, its
  docstring's paragraph on the shared package deleted; `catalog_matching/__init__.py` and `py.typed` go. The folder
  is part of the `p2pwatch.domain` tach module, with no module of its own.
- `packages/matching/tests/domain/test_*.py` to `packages/crawler/tests/domain/matching/` (`test_ed2k_link.py` to
  `packages/crawler/tests/domain/`), `test_golden_corpus.py`
  beside them, `tests/fixtures/golden_*.yaml` to `packages/crawler/tests/fixtures/`; the crawler's
  `tests/application/conftest.py` reads the fixture there.
- Every `catalog_matching.domain` import becomes `p2pwatch.domain.matching`, `p2pwatch.domain.ed2k_link` for the link (`git grep -c catalog_matching --
  packages/crawler`: 88 files, 158 lines, `pyproject.toml` included).
- `rapidfuzz` joins the crawler's dependencies; `catalog-matching` leaves them, the root `pyproject.toml`'s workspace
  sources, source roots, poe tasks (deptry, mypy, pyrefly, pytest, unit coverage), `tach.toml` (its source root and
  module), and the ast-grep import rules' first-party list. `uv.lock` regenerated.
- `test_workspace_dependencies.py`: no workspace member depends on another.
- Records: `.claude/CLAUDE.md` (seven packages, the single-test example, the path-scoped table), `.claude/rules/matching.md`
  and `deploy.md` (their paths), `deploy/matcher.yml`'s two comments naming `packages/matching`,
  `docs/contributing/architecture.md` where it names the package; the hexagonal architecture spec's D3 marked corrected.
- A purely mechanical block: past both bounds, approved by the operator on 2026-11-07. Its report gives the diff's
  count of renames against the count of other hunks, which are the imports and records alone.

### Block 20: `validate-config` checks every file and lists their problems (D3)

- `ConfigProblem` (file, key or none, message) moves from the driving port to the domain; the driving port's
  `ConfigReport` keeps its tuple, now of every problem.
- `ConfigChecker`'s three methods return their file's problems (an empty tuple when it is valid) instead of raising;
  a file that cannot be read (`BrokenInputError` from `load_yaml`) is one problem of that file, with no key. The
  parses still stop at their first problem, which the adapter turns into one problem of its file: a file gives at most
  one in this block.
- `ValidateConfig` checks the three files and concatenates their problems; `validate-config` prints one
  `Invalid config: <file>: <key>: <message>` line per problem, its `error:` path for a broken file gone.
- Tests: the use case over the fake checker; the adapter with a broken file beside a wrong one; the command line.

### Block 30: the start refuses with every problem (D3)

- `InvalidConfigError` carries a non-empty tuple of `ConfigProblem`s in place of one key and message. The domain's
  parses, which do not know their file, raise in its place a domain `ConfigValueError(key, message)`, which the
  adapter turns into a problem of its file; it goes with the last parse, in block 110.
- `load_config` checks the three files, raises `InvalidConfigError` with every problem, and builds the config only
  when there is none.
- `${NAME}` interpolation lists every unset or ill-formed variable, then the file's parse runs on the document.
- The start prints one `Invalid config, refusing to start: <file>: <key>: <message>` line per problem, exit 1; today
  its line names no file.
- Tests: `load_config` with two wrong files; the interpolation's two unset variables; the command line.

### Blocks 40, 50 and 60: `crawler.yml` read by pydantic (D2 to D4, D7)

- Block 40 brings the dependency, the rule, the translator, the root model with the root keys, `search`, `backoff`
  and the root's 4.x keys. `observability`, `download` and `webui` are typed as a plain mapping, which the domain's
  section parses read: `_parse_observability`, `_parse_download` and `_parse_webui` become public until their block
  replaces them, and keep refusing the 4.x keys under them (`observability.metrics`, `webui.enabled`, a
  notification's `tag`). They run whether or not the root model holds, so each section still gives its first problem
  beside the root's.
- Block 50 models `observability` and `webui`, block 60 `download`; block 60 deletes `parse_crawler_config` and its
  helpers, `crawler_config.py` keeping the dataclasses.
- `pydantic` and `pydantic-core` join the crawler's dependencies (the latest 2.x, which the probe ran: 2.14.3, core
  2.50.4; `PydanticCustomError` is `pydantic_core`'s, so deptry needs both declared); an ast-grep rule refuses either
  import outside `packages/crawler/src/p2pwatch/adapters/driven/config/`, on the model of `no-sqlite-connect`.
- A pydantic model per section, `extra="forbid"`, `strict=True`, `allow_inf_nan=False` (main refuses `.inf` and
  `.nan`); the bounds today's parse holds (strictly positive, at most a day or 30 days, `factor` at least 1, non-empty
  strings and keyword list) as field constraints, `log_level` and `audience` a `Literal` of their closed set (strict
  mode refuses a string for an `Enum` field). The adapter builds `CrawlerConfig` from a valid model.
- The keys 4.x used: each removed key (today's list, plus `webui.host` and `webui.port`, ignored on purpose today) is
  a field that refuses with "was removed, delete it from crawler.yml", through a `PydanticCustomError` (a `ValueError`
  reads "Value error, ..."); `backoff` with "moved to 'search.backoff'"; a notification's `tag` with "was renamed
  'audience'". The new name's "Field required" beside a moved or renamed key is dropped (D7).
- `download`: every key present is checked whether or not `enabled` is true; the wiring keys are required only when
  it is.
- The rule across values, a backoff cap below its base, is a domain function over the built `CrawlerConfig`,
  returning its problems, which the adapter runs once the model is valid (D3).
- `validation_problems.py` turns a pydantic `ValidationError` into `ConfigProblem`s for the three schemas: the key
  from the error's location, each tagged union's tag carrying a mark no key can take (`~regex`) and dropped; the
  message pydantic's, without the value received (D7), ours as written for our errors.
- Tests: the domain's `test_crawler_config.py` cases that test the parse move to the adapter's tests, each refusal
  still refused (`test_a_number_that_is_not_finite_is_refused_by_name` included); every problem of one file listed;
  an unknown key at each level; the removed, moved and renamed keys, one problem each; `download` disabled with a
  wrong value; the rule's own valid and invalid cases; an unknown key and a string where a mapping is expected, each
  holding a resolved `${NAME}`, whose value is absent from the line.

### Blocks 70 and 80: `targets.yml` read by pydantic (D2 to D4, D6, D7)

- Block 70: `targets_from_document`, called by `read_targets`, still through `parse_targets`; the call sites in the
  tests read through it (`git grep -c "parse_targets(" -- 'packages/*/tests'` outside `test_validation.py`: 14 lines
  in 9 files), so that block 80 changes the parse alone.
- Block 80: a schema per level (the file, an episode, a segment), strict, `extra="forbid"`; `status` a `Literal`
  defaulting to `lost`; a control character in a letter refused through the domain's `has_control_character`, as
  today. The adapter builds the `TargetSegment`s.
- The rule across values, a duplicate `target_id` (letters compared upper-cased), a domain function returning every
  duplicate, run once the shape holds.
- `parse_targets` leaves the domain.
- Tests: each refusal of today's `test_validation.py` targets cases, every problem listed, a numeric title and `2.7`
  refused.

### Blocks 90, 100 and 110: `matcher.yml`'s shape read by pydantic (D2 to D4, D6, D7)

- Block 90: `matcher_config_from_document`, called by `read_matcher_config`, still through `parse_matcher_config`;
  the call sites in the tests read through it (`git grep -c "parse_matcher_config(" -- 'packages/*/tests'` outside
  `test_validation.py`: 29 lines in 9 files).
- Block 100 models the fragments, the leaf tokens and the 4.x names; the conditions, rules and vetoes are typed as
  plain values that the domain's parse still reads, its condition and rule parses public until block 110, which models
  them and deletes the structural half of `validation.py`.
- A token is a tagged union over its shape (`keyword`, `regex`, `coverage`, `attr_between`, or a condition). The
  discriminator is a function that returns the shape's tag, or a refusing tag for no shape or two, whose model refuses
  in a `mode="before"` validator with today's words and keys (`unknown token shape: keys [...]`, `a leaf token has
  exactly one type-key, got [...]`): a discriminator that raises drops every other problem, and its static
  `custom_error_message` cannot name the keys.
- A condition (`all`, `any`, `not`) is recursive; an operand is a token name, a `{token: ...}` reference or a
  condition; a rule's `tier` and `scope` are `Literal`s, its name refuses a control character.
- The 4.x names, each refused with its 5.0 name in the shape (D3): `min` and `fuzz` on a coverage token or reference,
  `size_mb` and `duration_sec` in `attr_between`, and a regex holding `{segment}` (a validator on the regex field);
  the new name's "Field required" beside them dropped.
- The adapter builds `MatcherConfig`; fragment expansion and its two checks (a fragment named after a target
  placeholder, a fragment citing a fragment) stay domain functions it calls. Until block 120 the adapter calls the
  domain's `validate_config` on the built config, first problem only.
- Tests: each structural refusal of `test_validation.py` still refused, every problem listed, strict values.

### Block 120: the matcher's rules across values, every one listed (D3, D7)

- `validate_config` becomes a domain function returning every problem: unknown references (in a token, a rule, a
  veto), a duplicate veto, an override on a token that is not a coverage one, each cycle, the depth bound (checked only
  when no cycle was found), each regex that does not interpolate or compile. `UnknownTokenError`, `CycleError` and
  `DepthExceededError` go with the exceptions.
- Tests: the graph cases of `test_validation.py`, a config breaking two checks listed whole.

### Block 130: a key written twice refused (D5)

- `load_yaml` reads with a `yaml.SafeLoader` subclass that records each mapping key written twice, its key path and
  both lines (from the nodes' marks), and returns them as problems with the document; the alias-cycle and UTF-8
  checks stay.
- Tests: a key twice at the root and in a section, both listed; a merge key's override is not a duplicate.

### Block 140: closing block

- The holistic review's findings, `BACKLOG.md` reconciled, the handoff; the Wrap's rows of section 4.

## Appendix B. Acceptance, in detail

| Row | Command or test, and the output that fails it |
|---|---|
| 4.1.0's files | a test over `git show v4.1.0:deploy/{crawler,matcher,targets}.yml` committed as fixtures, its two notifications uncommented: exactly the 14 problems of appendix C, each by file and key; fails on a missing or an extra one |
| The start | the command line's test over the same fixtures: one `Invalid config, refusing to start:` line per problem, exit 1 |
| A broken file beside a wrong one, two and three wrong values, two unset variables | block 20's and 30's tests of the adapter and the command line |
| An unknown key, `.inf`, strict values | blocks 40 to 110's schema tests, one case each |
| A key written twice | block 130's loader tests |
| A failing token cited twice | block 110's test: the definition's problem alone |
| Two cross-value problems | block 120's test |
| The operator's 4.x files | `validate-config` from the stack's top on `/home/geoffrey/Projets/mulewatch/{crawler,targets,matcher}.yml` read in place, its `${NAME}` set: fails unless the 15 lines of appendix C, nothing else |
| Equal domain objects | a probe that loads `deploy/`'s files and the operator's migrated copies with `main`'s parse (a `git worktree` at `70e68d21`) and the lot's, comparing the `repr` of each config object: fails on any difference |
| pydantic confined | the ast-grep rule's own tests, a valid and an invalid case |

## Appendix C. Facts

Measured on `main` at `70e68d21`, 2026-11-07, by the lead and the spec's reviewer; probes in the lead's scratchpad.

| Fact | Result |
|---|---|
| The operator's 4.x files, each refusal removed then parsed again | 15: in `crawler.yml` the 9 removed keys (`cycle_interval_seconds`, `decision_poll_interval_seconds`, `keyword_pause_max_seconds`, `keyword_pause_min_seconds`, `observability.metrics`, `port_sync`, `search_poll_budget_seconds`, `search_poll_interval_seconds`, `webui.enabled`), `backoff` moved, `tag` in each of the 3 notifications; in `matcher.yml` `min` on `title_hit` and `{segment}` in `segment_id`; `targets.yml` accepted |
| 4.1.0's shipped files | the same 9 removed keys and `backoff`; with its two commented notifications uncommented, their 2 `tag`s; `matcher.yml` the same 2 (identical to the operator's): 14 |
| The 4.x `crawler.yml` key paths | 41 distinct paths, lists collapsed: each read, or removed, moved, renamed, or under one of these |
| The policy files' keys (`deploy/`'s, the operator's, 4.1.0's, `golden_targets.yaml`) | none that nothing reads |
| Values D6 refuses in those policy files | none (103 episodes each, 22 in the golden fixture) |
| PyYAML's `safe_load` on a key written twice | the last kept, no error; a merge key's override is not a duplicate |
| pydantic 2.14.3: field errors of nested models, an unknown key, a removed key as a refusing field | all listed in one `ValidationError`, a `PydanticCustomError`'s message kept verbatim |
| pydantic: a moved or renamed key's new name, required | a second error, "Field required" |
| pydantic: a model validator when a field fails | not run; run when every field holds |
| pydantic: a callable discriminator | raising inside it drops every other error; a refusing tag's `before` validator is listed with the rest |
| pydantic: `strict=True` | an int accepted for a float; a string refused for an `Enum`, accepted for a `Literal`; `.inf` accepted without `allow_inf_nan=False` |
| pydantic: an error's value received, after `${NAME}` interpolation | an unknown key, a mapping type error and a misspelled section carry the resolved value, a password or a webhook token included |
| `from pydantic import BaseModel` | about 14 MB resident |
| cattrs 26.2.1 (the alternative weighed) | every error listed while structuring dataclasses; fewer extension points |
