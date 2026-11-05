# CLAUDE.md

## What this is

`p2pwatch` continuously surveils the eMule network (eD2k + Kad, via an aMule client driven over amuleapi, its REST surface) to recover lost-media episodes of the French dub of *Keroro mission Titar* (aired 2008 on Teletoon), cataloguing all available metadata along the way.

A uv workspace of eight packages under `packages/`: the crawler `p2pwatch` (with its in-process webui), `p2pwatch_amule` (the aMule container's boot step and port-sync), `catalog_matching` (the matching engine), `pytest_settings` (shared test configuration), and four `*_checks` / `amule_bump` dev tooling packages never shipped in a prod image. A node is two containers: the core `p2pwatch` and `p2pwatch-amule` (compose service `ed2k`).

## Orientation

The live state, history, and recommended next step are deliberately **not** in this file (they would rot here). They live in:

- `agents/handoffs/`: one continuation guide per lot (`<ISO date> - handoff - <context>.md`). **The newest is the entry point**: current state, what was just built, learned pitfalls, next step, and what is *not yet validated against real hardware*.
- `agents/workflow.md`: how work moves (tiers, phases, the stacked blocks, pull request bodies, Wrap, defect classes, evidence, review findings). **Read it before starting a lot or a block.**
- `agents/specs/2026-06-10-crawler-mvp-design.md`: the authoritative MVP design (17 sections). Other dated specs in that dir record each subsystem's design + decisions; `agents/plans/` is historical, no plan is written since a tier Spec lot's spec is its brief.
- `docs/`: the operator's site (install, operate, troubleshooting); `docs/contributing/testing.md`: every test suite, the integration markers, prerequisites.
- `agents/reference/`: dated empirical findings (amuled, the instruction measurements); the live API reference is aMule's own `docs/api/REFERENCE.md`, in the source tree the image builds from.
- `BACKLOG.md` (repo root): what the project intends to do next, one entry of at most two lines each, linking the spec that holds the detail. **Read it before proposing work**, and write to it only after the operator has agreed. It carries no history: an entry is deleted when it ships or is dropped, never annotated. What reaches it (defect class 3, a review finding's exit) is in `agents/workflow.md`.
- Releases: an annotated tag `vX.Y.Z`, **pushed**, the milestone in its message (`v1.0.1 - performance patch`), publishes the image and the GitHub release. `latest` is the newest release, never the tip of `main`, which is tested through the `main` tag. A release is the operator's decision (`agents/workflow.md`, Wrap).
- `SECURITY.md`: the signed images, their SBOMs and VEX files.

## Design invariants

- **The catalog records files and, where a protocol publishes one, the pseudonymous identifier of the source that shared them**, so that a researcher can recognise a recurring sharer and contact a possible archivist. It never stores a peer's network address (IP, port, country), and never links identifiers across networks.
- **The crawler never reads downloaded bytes, and never touches the filesystem of the output directory.**

## Commands

The gate lives in `pyproject.toml` under `[tool.poe.tasks]` (poethepoet) as the single source of truth: the pre-push hook and CI both call it. `uv run poe` lists every task with its `help`.

```bash
uv sync --dev        # install (scripts/setup-dev.sh also installs the pre-push hook)
uv run poe check     # THE FULL GATE (lint-all + test): the pre-push hook and CI run exactly this
uv run poe fix       # auto-fix everything mechanical: ruff --fix + ruff format + sqlfluff fix
```

**Before hand-fixing lint / formatting / SQL, run `uv run poe fix`**: don't spend turns rewriting by hand what a fixer applies mechanically; review its diff instead.

**`poe check` ends with `GATE GREEN`**; red, its last lines name every failed static check (`Subtasks 'lint', 'type-check' returned non-zero`), each one's output above: don't pipe it through `tail` and rerun it to find out.

**The gate is PER PACKAGE** (`cd packages/<pkg> && uv run pytest`; a root `pytest` collects nothing). Every `tests/` directory is a package, so a test module is `tests.<path>` and imports its helpers as such (`from tests.fakes.adapters.driven.fake_upstream_client import FakeUpstreamClient`).

**Single test** (the package-wide `--cov-fail-under=100` makes a lone test "fail": disable coverage):

```bash
( cd packages/matching && uv run pytest tests/domain/test_engine.py::test_evaluate_real_62a_is_download_via_first_rule_on_62a --no-cov -q )
```

Integration suites (Docker, deselected by default): `docs/contributing/testing.md`.

**Symbols through Serena** (`find_symbol`, `find_referencing_symbols`, `rename_symbol`), backed by the language server: it sees every reference and every override, `grep` sees strings. Read `.claude/rules/serena.md` before a rename.

## Hard rules

- **Clean / Hexagonal** (`agents/specs/2026-10-18-hexagonal-architecture.md`): six hexagons never import one another. A hexagon's rings are `domain/`, `application/` (`ports/{driving,driven}/`, `use_cases/`, `steps/`, at most one `<x>_lifecycle.py`), `adapters/{driving,driven}/` and `composition/`; imports point inward, and an adapter never imports another adapter.
- **Every module is declared in `tach.toml`** with exactly the dependencies it uses: a new module or a new import across modules is a new entry there, never a `# tach-ignore`.
- **A contract per contracted port, or per Writer/Reader pair**: `<Port>Contract` or `<Thing>StoreContract`, an ABC in `tests/contracts/` at the mirror of the port, whose tests state the port's docstrings; each implementation, its fake included, subclasses it as `Test<Implementation>` in its own test module.
- **A test never patches a module** (`monkeypatch`, `unittest.mock.patch`): what it tunes is a parameter, a port or a callback `Protocol`.
- **Only the clock adapters read the system clock or sleep**: everything else injects `WallClock` or `MonotonicClock`.
- **No I/O in the core**: `domain/` and `application/` import only what `ast-grep/rules/*-imports.yml` lists; a module that does I/O is an adapter.
- **Strict TDD**: write the failing test first, watch it fail, then the minimal code that passes it.
- **Python only** (>=3.13), conventional commits.
- **One named teammate per block of a tier Spec lot** (Act) and **the holistic review once per tier Spec lot**, at the head of Wrap over the top of the stack (`agents/workflow.md`): the cross-cutting review regularly catches bugs, don't skip it. A lot of one block is offered its waiver and the operator decides; tier Direct has none.

## Naming

- **`Reader` and `Writer` name ports over our own state only (databases, files, memory)**: such a port is a `<Thing>Writer` or a `<Thing>Reader`, never both, and a `Writer` is always half of a store: its `<Thing>Reader` reads what it wrote, and one adapter implements the pair.
- **An adapter is named by the system, the thing and the role**: `SqliteObservationStore`, `GluetunForwardedPortClient`. The system is what would need another adapter if replaced (`AmuleApi`, `Sqlite`, `Posix`, else `Filesystem`), never a syntax (`Json`, `Yaml`).
- **`latest` is the most recent of a series; `last` only pairs with `first`.**
- **No abbreviation but the glossary's**, units and protocol names (`kbps`, `tcp`, `md4`, `ed2k`) aside.

The project's glossary (the shared words, what each means, what it is never called) is `.claude/rules/glossary.md`, which loads when you touch `packages/` or `agents/specs/`: read it before naming a concept anywhere else.

## Path-scoped rules

Claude Code loads each file when its Read, Edit or Write tool touches a matching path; **Serena's tools load none**: before working in one of these paths through Serena alone, Read its file first.

| File | Paths |
|---|---|
| `amule-container.md` | `packages/amule/`, `.github/` |
| `amuleapi.md` | the amuleapi adapter, its tests and `FakeAmuleApiServer`, `packages/amule/`, `agents/reference/` |
| `coverage.md` | every package's `src` and `tests` |
| `deploy.md` | `deploy/`, the config adapter, matching's tests |
| `docs.md` | `docs/` |
| `glossary.md` | `packages/`, `agents/specs/` |
| `matching.md` | `packages/matching/`, `deploy/matcher.yml`, `deploy/targets.yml` |
| `merge.md` | the `merge` use case, the catalog copier, the database opener, the command line |
| `packaging.md` | every `pyproject.toml`, `tach.toml`, every `Dockerfile` |
| `persistence.md` | the SQLite adapter and its tests |
| `serena.md` | every `.py` under `packages/` |
| `stores.md` | the SQLite adapter, the in-memory stores |
| `text-encoding.md` | the config adapter, the amuleapi mapper, `value_bounds.py`, the `merge` use case |

## Workflow

Tiers, phases, blocks, the stack, pull requests, Wrap and review findings: `agents/workflow.md`.
