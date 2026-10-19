# Serena and the language servers (lot 2 of the gate tooling umbrella)

Status: tier Spec lot. Discuss opened 2026-10-16, closed 2026-10-17 on the operator's decisions: pyrefly is
Serena's language server, mypy keeps the gate, ty is re-examined only when it reaches parity, and the ports stay
`Protocol`s for now. The spec review of 2026-10-17 measured what turning them into ABCs would take and found it to
be architecture work (overlapping ports, ports outside `ports/`, the composition's factories), which the operator
deferred to a lot of its own; what it found is kept below for that lot. Every measurement here is in
`agents/reference/2026-10-16-python-language-server-bench.md`: the bench of 2026-10-16, the latest-release
re-measurements of section 4 and the spec review's re-measurements of section 11, both of 2026-10-17. This lot
carries out U-D11 of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`; its lot order is U-D12.

## Why

Serena's tools are only as good as the language server behind them, and the operator wants a Serena that spares
manual operations. The bench measured the five servers Serena 2.0 can drive: no server renames a structural
implementation, only one follows the nominal edge, and Serena applies whatever a server returns without
filtering or checking it. This lot runs the best server for this tree, configured so that it answers completely,
versions that configuration, and writes down what no server does.

## What the bench established (the claims this lot rests on)

- **The server choice is the only lever for rename quality.** For all five servers the rename set is exactly the
  references set; `rename_symbol` applies the returned workspace edit verbatim, filters nothing, re-checks nothing
  and does not warn on a small edit set (`serena/code_editor.py:409-443` of the installed Serena 2.0; its only
  guards are a `None` answer and zero changes). One server serves a file: the first listed in `language_servers`
  that does not ignore the path wins (`serena/ls_manager.py:172-188`).
- **Only pyrefly follows the nominal edge, and only downwards.** Renaming a base method reaches its overrides (4 of
  4 sites), and an ABC method its implementations (3 of 3), on pyrefly 1.2.0 and 1.4.0; pyright, basedpyright and
  ty rename the declaration and at most the calls typed by the base. Renamed from an override or an
  implementation, pyrefly never climbs to the base, and two sibling classes declaring the same method are never
  linked (bench 11).
- **No server reaches a structural implementation by rename.** On the fixture's `Protocol` case pyrefly reaches 5
  of 6 sites, missing the class that implements the port without inheriting it; the others reach 2. On this tree,
  renaming `CatalogRepository.record_observation` from the port edits 4 sites with pyrefly and 2 with the three
  others, never the adapter; from the adapter, 70 sites with pyrefly and 71 with the others, never the port
  (bench 11).
- **pyrefly needs two settings to answer completely on this tree** (bench 11). Its interpreter path: Serena hands
  it its own interpreter as `pythonPath`, and without `[tool.pyrefly] python-interpreter-path` the workspace
  members do not resolve and a rename collapses to its declaration. Its indexing mode: Serena declares it ready
  before it has indexed, and in the default mode the first rename sent at that instant returned 1 of 75 sites on 5
  runs of 5, while `--indexing-mode lazy-blocking` returned 75 of 75 on 5 of 5, the first request blocking about
  275 ms. Serena retries only on the `-32800` and `-32801` errors, so it applies the partial edit.
- **pyrefly does not resolve one test module importing another** (`from tests.application.test_run_download_cycle
  import FakeCatalogReads`): eight packages have a top-level `tests`, and no import root under D3's configuration
  reaches them. A method overridden in a class inheriting through such an import is not renamed with its base;
  mypy stays green, since the stale override becomes an extra method, and only a test that needed the override
  fails (bench 11). Eight such imports exist, five in the crawler and three in amule_bump.
- **The failures no server closes**: the uses inside a pytest test body when the fixture is renamed (pyrefly 3 of
  5 sites, the others 1 of 5, the file broken either way); an attribute only a Jinja template reads; a name inside
  an ordinary string, although pyright and basedpyright rewrite the `__all__` entries (bench C6, C7); and the
  `dataclasses.replace` keyword.
- **The latest releases move nothing that matters here**: basedpyright 1.39.9 to 1.40.2 answers site for site
  identically on every failing case; ty 0.0.25 to 0.0.89 lifts the closed-document gate and adds an implementation
  request that stays nominal, with all twelve renames identical; pyrefly 1.2.0 to 1.4.0 fixes the cross-module
  keyword argument and nothing of the edges. All three are PyPI's latest on 2026-10-17, and Serena's is 2.0.0.
- **Serena's own behaviour**, read from the installed source: it never calls `workspace/symbol` (its `find_symbol`
  walks the filesystem and asks document symbols per file, cached by content hash); `find_referencing_symbols` is
  `textDocument/references` alone; `get_diagnostics_for_file` opens the file before asking; and a server's version
  pin is overridden per project through `ls_specific_settings.<server id>.<key>`, the key declared in each server
  module (`pyrefly_version` at `solidlsp/language_servers/pyrefly_server.py:136`, `ty_version` at `ty_server.py:49`)
  and read at `solidlsp/dependency_provider.py:280-281`; the same pyrefly module reads `indexing_mode`
  (`pyrefly_server.py:124-126`). Serena pins pyrefly 1.2.0 and ty 0.0.25.
- **The gate's side, measured on this tree**: `mypy --strict` reports zero diagnostics over the eight packages
  (333 files) in 12.58 to 12.69 s cold; ty 0.0.89 runs in 0.126 s, but six `--strict` flags have no complete ty
  rule, and ty skips by design a `# type: ignore[...]` code carrying no `ty:` prefix, so the 36 suppression
  comments of this tree (at `9e2cba3`) are inert to it and the diagnostics they carry (37 at default levels, 39
  with the docs' strict block) fail a ty run.

## Decisions

- **D1. pyrefly is Serena's language server, pinned to 1.4.0 and run with `lazy-blocking` indexing**, through
  `ls_specific_settings.python_pyrefly` (`pyrefly_version: "1.4.0"`, `indexing_mode: lazy-blocking`), and
  `python_pyrefly` is the only entry of `language_servers`. Why: with the ports structural, no server renames a
  port through to its implementers, so the servers differ on the rest. pyrefly renames through nominal
  subclasses, which this tree has (fakes extending fakes, a test double extending an adapter), and none of the
  others does; it takes about half of basedpyright's memory on this tree (236 against 422 to 432 MiB, process tree
  after the same request sequence, bench 11); it diagnoses the whole tree; and it is the server the deferred
  architecture lot needs if the ports become nominal. basedpyright's chief advantage meanwhile, listing a
  `Protocol`'s structural implementers, was weighed and left aside (the operator, 2026-10-17). The pin keeps the
  1.4.0 keyword argument fix that Serena's own 1.2.0 lacks; `lazy-blocking` because the default mode hands Serena a
  partial rename that Serena applies, for about 275 ms on a fresh process's first request (bench 11). The caveat a
  clone must know: a project's `ls_specific_settings` is merged over the global ones only when the project is
  trusted (`serena/project.py:669-677`), trust is set only in the user's global `trusted_project_path_patterns`,
  and the template a new Serena install writes trusts nothing (`serena/resources/serena_config.template.yml`). An
  untrusted clone therefore starts pyrefly 1.2.0 in the default mode, partial first rename included; D5 writes it
  down. This machine trusts `**`.
- **D2. `.serena/project.yml` is versioned**, with `.gitignore`'s `.serena` line becoming `.serena/*` plus
  `!.serena/project.yml`. Why: U-D11 states it, and without it every clone falls back to pyright, which would
  quietly undo D1. The negation form is required because git cannot re-include a file inside an ignored directory.
  The nested `.serena/.gitignore` is not versioned today and stays so: in a clone, the root `.serena/*` is what
  keeps `cache/` and `project.local.yml` out (the latter overlays `project.yml` per machine, which is its purpose).
- **D3. `[tool.pyrefly]` joins `pyproject.toml`, holding a relative `python-interpreter-path` and no preset.** Why:
  the interpreter path is load-bearing, since Serena's `pythonPath` points at its own interpreter and pyrefly does
  not discover `./.venv` alone (bench 11); it alone resolves the eight members and the root `.venv`, `search-path`
  being unnecessary on the real tree (bench 4.3); and the section's presence lifts the server out of its silent
  `basic` preset (bench 5.6). The path is written relatively, `"./.venv/bin/python"`, measured in that form on a
  clone with its own venv (bench 11); the absolute form would be wrong on every other clone. `preset = "strict"`
  is rejected for now: its extra findings on this tree are of the typeshed-`Any` family, which the bench measured
  on the fixture only, and it stays one line away.
- **D4. mypy keeps the gate; ty is not added to it.** Why: measured, six `--strict` flags this tree relies on have
  no complete ty rule, and a ty run fails on the 36 ignores that mypy's codes carry. Speed alone (0.126 s against
  12.6 s) does not trade for a lost check.
- **D5. What no server does, and how to use the one chosen, goes to `AGENTS.md`'s Gotchas**, each item citing the
  bench report's section: a port method is renamed from the port and again from each implementer, which no server
  links to it (bench 11); an override in a test class whose base comes from another test module is not renamed
  with its base, and mypy does not notice (bench 11); a pytest fixture's uses, a Jinja-read attribute, a name
  inside a string (`__all__` included, under pyrefly) and a `dataclasses.replace` keyword are never renamed (bench
  3.1, 5.7); and D1 holds only in a project Serena trusts. Why: U-D11, and because a Serena-only prompt would miss
  every session that does not activate Serena, whereas the Gotchas are read by every agent and teammate.
- **D6. `BACKLOG.md` gains two entries.** Adopt ty, first as the gate's type checker and then for Serena's seat,
  once the parity conditions below are met. And the ports and composition architecture lot, whose inputs are the
  section "For the architecture lot". Why: the operator asked for both to be recorded with their pointer here, and
  their detail belongs in this document rather than in a two line entry.

## For the architecture lot

Measured or decided during this lot's review, kept here so that the deferred lot starts from it rather than from a
re-measurement. None of it is done in this lot.

- **The rename once a port is an ABC its implementers inherit** (bench 11): pyrefly renames
  `CatalogRepository.record_observation` from the port across all 75 code sites in 12 files, `mypy` clean and the
  crawler's suite green after the edit; the other three servers stay at 2 sites. Renamed from the adapter, pyrefly
  stops at 70 and `mypy` rejects the tree (`Cannot instantiate abstract class`).
- **Two ports declaring the same method** (bench 11): `CatalogRepository` redeclares `DownloadCatalogReader`'s
  three reads, `connect` is in `SearchClient`, `StatusClient` and `DownloadClient`, `close` in `SearchClient` and
  `DownloadClient`. As sibling ABCs, a rename from either leaves the other abstract and `mypy` fails; one extending
  the other renames cleanly from the base, but the operator found the general repository extending a use case's
  view semantically wrong. Of the three reads, `download_candidates` and `latest_observation` are called only
  through `DownloadCatalogReader` and `best_observation` through both (`application/run_download_cycle.py`,
  `application/decisions.py:80`): the operator's leaning, not a decision, is that each method be declared by one
  port (dropping the two from `CatalogRepository`), and that `connect` and `close` stay duplicated with a Gotcha.
- **Ports declared outside `ports/` that an adapter implements**: `DownloadRepository` and
  `DownloadCatalogReader` in `application/run_download_cycle.py`, `DownloadSourceClient` in `composition/app.py`.
  Inheriting them would make an adapter import a use case, and `AmuleApiClient` import `composition/app.py`, which
  imports it: a cycle. The operator agreed they move into `ports/` if the ports become nominal.
- **Three composition seams, ports by form only**: `MuleClient` and `DownloadSourceClient` are intersections that
  type the return of the two client factories, which hand one session to two consumers (`composition/app.py:256-270`,
  `484-505`); `WebuiServer` exists only so that the composition's tests can replace uvicorn. The operator's view:
  wiring is a concern between units, so the composition should be built without injected factories and tested in
  integration, which deletes all three; that amends `AGENTS.md`'s unit coverage rule and reworks the 1,881 lines
  of `tests/composition/test_app.py` and `test_main.py`. (Corrected 2026-10-19: lot 1a removed `WebuiServer` and
  the intersection types; lot 2's spec, `2026-10-19-hexagon-p2pwatch.md`.)
- **What an ABC conversion breaks mechanically**: `@runtime_checkable` on `MetricsSink`, `Notifier` and
  `Telemetry` (`ports/telemetry.py:11,16,23`) raises on a non-`Protocol`; `LoopCrawlerControl`'s `__slots__`
  (`adapters/crawler_control_loop.py:28`) stop locking once it inherits a slotless port, and the operator decided
  they would then go with the test that reads them, being only the rewrite of a `vars()` test (gate tooling lot,
  block 160) (Corrected 2026-10-19: that test reads the `__slots__` tuple, with no `vars()`; lot 2's spec); `SearchClient.channels` and `WebuiServer.should_exit` are attributes, not methods.
- **A guard for whichever form wins**: an ast-grep rule refusing a `Protocol` base under `packages/*/src` was
  prototyped and matches today's 26 ports, `typing.Protocol`, `Protocol[T]` and multi-line base lists included.
- **The `tests.*` import gap** of the claims above, which a move of the shared doubles into
  `packages/crawler_testing` (and its counterpart for amule_bump) would close for pyrefly.

## ty: the parity conditions

Recorded here so the day they close, the decision is a reading rather than a re-measurement. Nothing in this lot
depends on them.

**Where the citations come from**: every issue link on this page was read through
`gh api repos/{microsoft/pyright,astral-sh/ty}/issues/<n>` on 2026-10-17. All are open except pyright 7308,
closed labelled `as designed`: it concerns finding references between an `@abstractmethod` and its
implementations, which the Pylance team answered works in Pylance and not in pyright by design, and pyright's
rename is its references set (bench 5.1). The bench report itself cites only ty#4381 and ty#200, so the other
citations are checked here rather than there.

**The six `--strict` flags with no complete ty rule** (measured on this tree, ty 0.0.89; bench 7 groups the untyped
rows into one capability and counts four, they are split here because their upstream states differ):

| Capability | State upstream |
|---|---|
| `disallow_untyped_calls` | [ty#4381](https://github.com/astral-sh/ty/issues/4381), open |
| `no_implicit_reexport` | [ty#200](https://github.com/astral-sh/ty/issues/200), open |
| `strict_equality` | partly covered: `redundant-condition-strict` (opt-in) catches the comparison inside an `if`, not in a value position; the rest is [ty#576](https://github.com/astral-sh/ty/issues/576), open |
| `disallow_subclassing_any` | no issue found: the absence of tracking is itself the finding |
| `disallow_untyped_defs`, `disallow_incomplete_defs` | deliberate: ty's typing FAQ points at ruff's `ANN` rules, so these are reachable by configuration rather than by waiting (this repository's ruff selection has no `ANN` today) |

**What blocks a swap besides those**: ty reads a `# type: ignore[...]` code only when it carries a `ty:` prefix,
so the 36 mypy-coded suppressions of this tree suppress nothing for it (the mechanism identical on 0.0.25, 0.0.87
and 0.0.89, the totals not). Any swap has to rewrite them, and while both checkers run, as two comments
(`# type: ignore[arg-type]  # ty: ignore[invalid-argument-type]`): a combined bracket fails mypy `--strict` as an
unused ignore, and a `ty:` code that does not name the real rule keeps the error and adds an
`unused-type-ignore-comment` warning, which also fails.

**Capabilities pyrefly has and ty lacks as a language server** (measured on the frozen fixture, at each server's
latest release):

| Capability | pyrefly | ty |
|---|---|---|
| Rename follows the nominal edge (base to overrides, ABC to implementations) | yes | no: [ty#3347](https://github.com/astral-sh/ty/issues/3347), under the parity umbrella [ty#3589](https://github.com/astral-sh/ty/issues/3589) |
| Cross-module keyword argument renamed | yes since 1.4.0 | yes |
| Pull diagnostics on a document never opened | answered | silent empty report since 0.0.84 (a regression in observability from the loud error it replaced) |
| `workspace/diagnostic` | not measured | advertised and never answered (300 s, no `$/progress`) |
| `typeHierarchy` | not measured | advertised, `supertypes` and `subtypes` answer `-32601` |
| Pytest fixture rename | 3 of 5 sites, file left broken | 1 of 5 sites, file left broken |

Both fail identically on the shapes no server handles, so those are D5's Gotchas rather than parity conditions.

## Blocks

| Block | Branch | What |
|---|---|---|
| 10 | `chore/serena-pyrefly` | This spec and D6's two `BACKLOG.md` entries in the first commit; `.serena/project.yml` versioned with D1's settings, and its `.gitignore` lines; `[tool.pyrefly]` in `pyproject.toml` with the relative interpreter path; `[tool.pyright]`'s comment amended, since Serena no longer reads that section; the `AGENTS.md` Gotchas of D5; the live verifications of Acceptance 2 and 3 with their numbers; `uv lock`, run only to confirm the new table leaves `uv.lock` untouched, which the report states either way. A handful of files, all configuration and prose. |
| 20 | `docs/serena-lot-wrap` | Closing block: the holistic review's findings if the operator does not waive it for a lot of one block, `BACKLOG.md` reconciled, the handoff. |

## Acceptance

1. **A fresh clone gets pyrefly.** `git ls-files .serena/project.yml` prints the path, `git check-ignore --no-index
   .serena/project.yml` exits non-zero (`--no-index` because git otherwise skips a tracked file, so a force-added
   file under the old `.serena` line would exit non-zero too; and without `-v`, which prints negated matches and
   exits 0 either way), and the file names `python_pyrefly` with the 1.4.0 pin and `lazy-blocking`. Falsifier: the
   path is untracked, or `--no-index` reports it ignored, which is the state before this lot.
2. **The running server is pyrefly, at the pinned version and mode, and it serves this tree.** Observed live in
   block 10, whose report holds the evidence: Serena's language server child reads `/usr/bin/uv tool uvx -p 3.13
   --from pyrefly==1.4.0 pyrefly lsp --indexing-mode lazy-blocking` in `ps -ef` (`/usr/bin/uvx` re-executes as
   `uv tool uvx`), and `find_declaration` on a `catalog_matching` symbol used from the crawler lands under
   `packages/matching/src/`. The report also records the pre-lot answer, because on this tree the declaration
   resolves under pyright as well: the `.venv` editable installs point at this same checkout, so the
   discriminating part is the server's identity, version and mode, not the resolution. Falsifier: a `pyright`
   child process, a pyrefly at 1.2.0, or a command line without `--indexing-mode lazy-blocking`, which is what an
   untrusted clone gets (D1's caveat).
3. **A rename through Serena follows a nominal override.** In block 10, with `git status --porcelain` empty, one
   `rename_symbol` of `SqliteBackoffStateRepository/save_backoff_states` in
   `adapters/persistence_sqlite/backoff_state_repository.py`, counted with `git diff --stat`, then reverted with
   `git restore .` and `git status --porcelain` empty again; the same before the switch, under pyright. Expected:
   under pyrefly the diff renames the `def` of `_SavesRecorded.save_backoff_states` in
   `tests/application/test_search_tasks.py`, which overrides the method and calls it through `super()`; pyright
   leaves that `def` (block 10's pre-lot measure: 4 files, 9 sites, the `super()` call only). Falsifier: that `def`
   is not renamed in the pyrefly diff. (Corrected 2026-10-17: the file alone cannot fail, pyright reaches it
   through the super() call)
4. **The gate is green at every block.** `uv run poe check` at each block's tip. Falsifier: a red run.
5. **No operator-facing surface changes, and no code.** Between `main` and the lot's top branch, `git diff --stat`
   lists no file under `packages/`, `deploy/` or the migrations, and `uv.lock` gains no package name. Falsifier:
   any of those shows a change. The `[tool.pyrefly]` table of D3 is expected in the diff and is not a dependency:
   only pyrefly reads it.

## Out of scope

- The ports as ABCs, the overlapping ports, the ports outside `ports/`, the composition without injected
  factories and the `tests.*` import gap: the architecture lot of D6's second entry.
- ty as the gate's type checker, and its two LSP gaps: recorded above, tracked by D6's first entry.
- The test quality lot (U-D3 to U-D5, U-D13 to U-D15) and mutation testing: lot 3.
- The logic-free template guard on Jinja's syntax tree, and the fakes' contract tests: separate backlog entries.
- Renaming pytest fixtures, a Jinja-read attribute, a name inside a string, or a `dataclasses.replace` keyword:
  no server does any of them, so they are documented as Gotchas and left to the operator's judgement case by case.

## Adjacent backlog items

- **Serena and the language servers**: this lot's own entry; block 20 deletes it.
- **Contract tests for the fakes**: adjacent, and it stays open; it gains weight in the architecture lot, where a
  fake may come to declare its port.
- **Test quality** (lot 3) and **Mutation testing in the gate**: different lots, untouched. Lot 3 renames and
  deletes many symbols, so it meets D5's Gotchas first.
- **The logic-free template guard on Jinja's syntax tree**: touching templates, not ports.
- **Multi network stage 5**, **Sort the files view by first seen**, **A copy before a migration that rewrites
  rows**, **The webui in the visitor's time zone**, **Every stamp an integer of microseconds**, **The webui's read
  side**: none concerns the language server or Serena, so none is touched.

## Open

Nothing. The server and the gate were settled by measurement, the ports' form deferred by the operator with the
review's findings kept above.
