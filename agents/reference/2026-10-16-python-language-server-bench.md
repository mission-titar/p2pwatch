# Python language servers and ty, benched on p2pwatch (2026-10-16)

Six agents ran one protocol (`/tmp/lsp-bench/PROTOCOL.md`) against one frozen fixture and one copy of this
repository, and three later re-measured their server at its latest release. This note merges their fragments,
the re-measurements, and the follow-up runs their authors reported back with their commands while it was being
merged (4.1's unavailable pin, 7's ignore probes); every number here comes from one of those, each named where
it matters. The two runs this note's author made itself are flagged in place. The fragments, in full:

| Fragment | Covers | Raw evidence under |
|---|---|---|
| `/tmp/lsp-bench/out/pyright.md` | axis I, `python` | `/tmp/lsp-bench/pyright/` |
| `/tmp/lsp-bench/out/basedpyright.md` | axis I, `python_basedpyright` | `/tmp/lsp-bench/basedpyright/` |
| `/tmp/lsp-bench/out/ty.md` | axis I, `python_ty` | `/tmp/lsp-bench/ty/` |
| `/tmp/lsp-bench/out/pyrefly.md` | axis I, `python_pyrefly` | `/tmp/lsp-bench/pyrefly/` |
| `/tmp/lsp-bench/out/jedi.md` | axis I, `python_jedi` | `/tmp/lsp-bench/jedi/` |
| `/tmp/lsp-bench/out/checker.md` | axis II, ty versus mypy in the gate | `/tmp/lsp-bench/checker/` |
| `/tmp/lsp-bench/out/ty-latest.md` | the re-measurements of section 4, ty 0.0.89 | `/tmp/lsp-bench/ty-latest/` |
| `/tmp/lsp-bench/out/pyrefly-latest.md` | the re-measurements of section 4, pyrefly 1.4.0 | `/tmp/lsp-bench/pyrefly-latest/` |
| `/tmp/lsp-bench/out/basedpyright-latest.md` | the re-measurements of section 4, basedpyright 1.40.2 | `/tmp/lsp-bench/basedpyright-latest/` |

The raw JSON, session logs, scripts and captured output stay in those directories; this note references them
by path and quotes only the decisive line. Two decisions are being informed:

1. which language server Serena 2.0 should run on this repository (five candidates, axis I, cases C1 to C24);
2. whether `ty` can replace `mypy --strict` in the gate (axis II).

## 1. What, when, where

| Item | Value |
|---|---|
| Date | 2026-10-16 (fragments written between 21:21 and 23:44 local) |
| Machine | AMD Ryzen 5 7600X, 6 cores / 12 threads, 30 GiB RAM, Linux 7.2.6, Python 3.13.6 (stated verbatim in `checker.md`; the five axis I fragments ran the same host in the same session and nothing contradicts it) |
| Serena | `serena-agent` 2.0.0; the bundled client is `solidlsp` at `/home/geoffrey/.local/share/uv/tools/serena-agent/lib/python3.*/site-packages/solidlsp/` |
| uvx | 0.13.1 (`/usr/bin/uvx`) |
| mypy | 2.3.1, compiled (`<copy>/.venv/bin/mypy`, pinned by `mypy>=2.3.1` in the root `dev` group) |
| Fixture revision | `b050f86c735ac266f5c556054c21f4e92165d351` (re-checked for this merge with `git -C /tmp/lsp-bench/fixture rev-parse HEAD`; working tree clean) |
| Repository revision | `fd9d6814ad32220d96365bebc11271c0c29948de`, `main`, used by all six fragments for the repository side |

| Serena id | Server | Version resolved | Serena's pin | Says the fragment |
|---|---|---|---|---|
| `python` | pyright (`pyright-langserver`) | **1.1.403** | `PYRIGHT_VERSION = "1.1.403"` in `solidlsp/language_servers/pyright_server.py` | launched through `uvx`, not `npx`; `npx pyright@latest` would resolve 1.1.414 |
| `python_basedpyright` | basedpyright | **1.39.9** (based on pyright 1.1.411) | `BASEDPYRIGHT_VERSION = "1.39.9"` | launched through `uvx`; `npx basedpyright@latest` would resolve 1.40.2 |
| `python_ty` | Astral ty | **0.0.25** as a language server | `TY_VERSION = "0.0.25"` in `ty_server.py:21` | pin and resolution agree |
| `python_pyrefly` | Meta pyrefly | **1.2.0** (`serverInfo.name` = `pyrefly-lsp`) | `PYREFLY_VERSION` in `pyrefly_server.py` | pin and resolution agree |
| `python_jedi` | jedi-language-server | **0.47.0** (jedi 0.20.1) | Serena installs nothing and runs the bare `jedi-language-server` command from `PATH` | not installed on this machine, so every measurement used `uvx --from jedi-language-server==0.47.0` |
| axis II | ty, the checker | **0.0.89** (`uvx ty@latest`) | n/a | a different version from the one axis I measured: the language-server side was re-measured on 0.0.89 in 4.2, so the two axes now share a version (5.8) |

Two protocol deviations were absorbed by the fragments and are recorded here rather than as corrections: the
protocol told pyright and basedpyright to be installed with `npx`, and both fragments found Serena launches
them with `uvx` and mirrored Serena instead (recording the `npx` resolution as a side fact). The protocol also
told each agent to work on a copy, which every fragment did; no fragment wrote inside
`/home/geoffrey/Repositories/emule-indexer` (`git status --porcelain` empty at the end of each).

**Comparability check: passed.** All five axis I fragments report the fixture revision
`b050f86c735ac266f5c556054c21f4e92165d351`, each on its own pristine copy, and every one states the revision
explicitly. No fragment measured a different revision, so no fragment is excluded and no number here is
averaged across revisions. The fixture's own history holds two commits (`be21342 fixture` and the HEAD
`b050f86 no name collision with the size rename`), so content measured before that second commit would not
have been comparable; none was. **Three of the five servers were then re-measured at their latest releases**
(ty, pyrefly, basedpyright); section 4 holds the pins, the override mechanism, the latest versions and every
delta, and it states which two servers were not re-measured.

## 2. The fixture, reproduced in full

`/tmp/lsp-bench/fixture` at `b050f86`, ten files, no dependency installed. Nine `.py` files plus one template.

`pyproject.toml`:

```toml
[project]
name = "lspfix"
version = "0.1.0"
requires-python = ">=3.13"
```

`lspfix/__init__.py`:

```python
from lspfix.impl import Widget
from lspfix.ports import Port

__all__ = ["Port", "Widget"]
```

`lspfix/base.py`:

```python
class Handler:
    def handle(self, event: str) -> str:
        return event


class Upper(Handler):
    def handle(self, event: str) -> str:
        return event.upper()


class Lower(Handler):
    def handle(self, event: str) -> str:
        return event.lower()
```

`lspfix/ports.py`:

```python
from abc import ABC, abstractmethod
from typing import Protocol

from lspfix.widget import Widget


class Port(Protocol):
    def render(self, widget: Widget) -> str: ...


class Drawable(ABC):
    @abstractmethod
    def draw(self) -> str: ...


class Sink(ABC):
    @abstractmethod
    def emit(self, event: str) -> None: ...

    @property
    @abstractmethod
    def label(self) -> str: ...
```

`lspfix/widget.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Widget:
    title: str
    size: int


def build(widget: Widget, limit: int = 10) -> str:
    return f"{widget.title[:limit]}"
```

`lspfix/impl.py`:

```python
import functools

from lspfix.ports import Drawable, Port, Sink
from lspfix.widget import Widget

DEFAULT_LIMIT = 10
WidgetName = str


class StructuralPort:
    def render(self, widget: Widget) -> str:
        return widget.title


class NominalPort(Port):
    def render(self, widget: Widget) -> str:
        return widget.title.upper()


class InheritedDrawable(Drawable):
    kind: str = "inherited"

    class Inner:
        pass

    def __init__(self) -> None:
        self._label = "d"

    @property
    def label(self) -> str:
        return self._label

    def draw(self) -> str:
        return self._label


class NominalSink(Sink):
    def emit(self, event: str) -> None:
        self.last = event

    @property
    def label(self) -> str:
        return "sink"


@functools.cache
def cached_load(name: str) -> WidgetName:
    return name
```

`lspfix/service.py`:

```python
from lspfix import Port, Widget
from lspfix.base import Handler
from lspfix.impl import DEFAULT_LIMIT, NominalSink, StructuralPort, cached_load
from lspfix.ports import Drawable
from lspfix.ports import Port as WidgetPort
from lspfix.widget import build

STRING_PORT = "Port"
STRING_LIMIT = "DEFAULT_LIMIT"


def use_everything(
    widget: Widget,
    port: Port,
    sink: NominalSink,
    handler: Handler,
    drawable: Drawable,
) -> str:
    alias: WidgetPort = StructuralPort()
    alias.render(widget)
    sink.emit("first")
    handler.handle("event")
    drawable.draw()
    small = widget.replace(size=4)
    text = f"{port.render(widget)} {small.title} {sink.label} {DEFAULT_LIMIT}"
    return text + cached_load("name") + build(widget, limit=3)


def patch_nothing(monkeypatch: object) -> None:
    monkeypatch.setattr("lspfix.impl.DEFAULT_LIMIT", 99)
```

`lspfix/broken.py`:

```python
from lspfix.widget import Widget, build


def broken() -> None:
    rows: int = "many"
    build(Widget("a", 1), limit=rows)
    Widget("a", 1).size.upper()
```

`lspfix/templates/page.html`:

```html
<!doctype html>
<title>{{ widget.title }}</title>
<h1>{{ widget.title }}</h1>
<p>{{ widget.size }}</p>
```

`tests/test_impl.py`:

```python
import pytest

from lspfix import Widget
from lspfix.impl import StructuralPort, cached_load
from lspfix.ports import Port as WidgetPort


@pytest.fixture
def widget() -> Widget:
    return Widget("t", 1)


def test_render(widget: Widget) -> None:
    port: WidgetPort = StructuralPort()
    assert port.render(widget) == "t"


def test_cached(widget: Widget) -> None:
    assert cached_load(widget.title) == "t"
```

### The 24 cases and their expected sets

The protocol's expected sets, with the counts it got wrong marked. Section 8 records the corrections; section 3
reports what each server actually did against the corrected set.

| Id | Request | Target | Expected set (protocol), corrected where marked |
|---|---|---|---|
| C1 | rename | `Port.render` to `paint` | 6 sites: `ports.py` def; `impl.py` `NominalPort.render`; `impl.py` `StructuralPort.render`; `service.py` `port.render(widget)`; `service.py` `alias.render(widget)`; `tests/test_impl.py` `port.render(widget)` |
| C2 | rename | `Drawable.draw` to `sketch` | 3: `ports.py` def; `impl.py` `InheritedDrawable.draw`; `service.py` `drawable.draw()` |
| C3 | rename | `Sink.emit` to `publish` | 3: `ports.py` def; `impl.py` `NominalSink.emit`; `service.py` `sink.emit("first")` |
| C4 | rename | `Handler.handle` to `process` | 4: `base.py` def; `Upper.handle`; `Lower.handle`; `service.py` `handler.handle("event")` |
| C5 | rename | `build`'s parameter `limit` to `max_rows` | protocol: 2; **`rg -w limit` finds 4** (see 8.2): the parameter, its read in the body, the two keyword call sites `service.py:26` and `broken.py:6`. `widget.replace(size=4)` must NOT change |
| C6 | rename | class `Widget` to `Card` | protocol: 13; **`rg -w Widget` finds 19** (18 code sites plus the `__all__` string) |
| C7 | rename | class `Port` to `Rendering` | protocol: 7; **`rg -w Port` finds 10, of which 9 must change** (8 code sites plus the `__all__` string; `STRING_PORT = "Port"` must not). Alias uses `WidgetPort` must NOT change |
| C8 | rename | `Widget.title` to `heading` | protocol: 4 code sites; **`rg -w title` finds 6 code sites** (the two `impl.py` reads are the extra) plus the template twice, which no server should find |
| C9 | rename | `Widget.size` to `count` | 3 listed: `widget.py` field; `service.py` `widget.replace(size=4)`; `broken.py` `.size.upper()`. **The second site does not exist as a member** (see 8.1), so only 2 are real |
| C10 | rename | `cached_load` to `load_cached` | 3 listed; `rg -w` finds 5 (the two import lines). The decorator line must not change |
| C11 | rename | `DEFAULT_LIMIT` to `MAX_LIMIT` | 3: `impl.py` def; `service.py` import; `service.py` f-string. The two `"DEFAULT_LIMIT"` strings must NOT change |
| C12 | rename | the pytest fixture `widget` to `a_widget` | 5: the fixture def, the parameter and the use in `test_render`, the parameter and the use in `test_cached` |
| C13 | implementations | of `Port` (structural Protocol) | `StructuralPort`, `NominalPort` |
| C14 | implementations | of `Drawable` (ABC) | `InheritedDrawable` |
| C15 | definition | `Widget` in `service.py`'s signature | the class in `widget.py`; say whether it landed on a re-export instead |
| C16 | definition | `WidgetPort` in `service.py`'s annotation | `class Port` in `ports.py` |
| C17 | hover | `cached_load`; `InheritedDrawable.label`; `Widget` | signature, and docstring when one exists (the fixture has none; four fragments measured the docstring half on the repository copy instead) |
| C18 | document symbols | of `impl.py` | which of `StructuralPort`, `NominalPort`, `InheritedDrawable`, its attribute `kind`, its nested class `Inner`, its property `label`, `draw`, `emit`, `DEFAULT_LIMIT`, `WidgetName`, `cached_load`, `__init__` appear, and with which kind |
| C19 | workspace symbols | `Lower`, `StructuralPort` | both, from a session where neither file was opened |
| C20 | containment | the symbol enclosing: the last line of `impl.py`; the `@functools.cache` line; the `return self._label` line of `InheritedDrawable.draw` | protocol: last line none or the module; **that line is inside `cached_load`** (see 8.3); decorator line `cached_load` or the module; return line `draw` |
| C21 | diagnostics | on `broken.py` | before the file is opened (pull) and after (push); two type errors exist by construction: `rows: int = "many"` and `.size.upper()` on an `int` |
| C22 | freshness | append `def late(sink: NominalSink) -> None:` / `    sink.emit("late")` to `service.py`, then ask references of `emit` | the new site appears in a live session without a restart, then the same after a restart |
| C23 | cost, fixture | startup to first answer; memory; latency of definition, references, rename, document symbols | numbers |
| C24 | cost and resolution, repository | the configuration each server needed for the eight members and the root `.venv`; start and index time; memory; latency on a named real symbol; diagnostics on a real file; whole tree or opened files | numbers and the configuration, verbatim |

## 3. The cases, one matrix per axis

Axis I: five language servers on the fixture. Cell = sites found / sites that must change (a count), or a
binary verdict where the criterion is binary. Every cell's command and decisive output line are in the evidence
list that follows each matrix; the raw JSON is in the fragment directories named at the top of this note.

### 3.1 Renames, C1 to C12

| Server | C1 (6) | C2 (3) | C3 (3) | C4 (4) | C5 (4*) | C6 (19*) | C7 (9*) | C8 (6*) | C9 (2 real) | C10 (5*) | C11 (3) | C12 (5) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pyright | 2 | 2 | 1 | 2 | 4 | 19 | 9 | 5 | 2 | 5 | 3 | 1 |
| basedpyright | 2 | 2 | 1 | 2 | 4 | 19 | 9 | 5 | 2 | 5 | 3 | 1 |
| ty | 2 | 2 | 1 | 2 | 4 | 18 | 8 | 5 | 2 | 5 | 3 | 1 |
| pyrefly | 5 | 3 | 3 | 4 | 2 | 18 | 8 | 5 | 2 | 5 | 3 | 3 |
| jedi | 4 | 2 | 1 | 2 | 2 or 3 | 18 | 8 | 5 | 2 | 5 | 3 | 1 |

`*` marks a column whose expected count is the corrected `rg -w` set, not the protocol's number (8.2). In C8 all
five servers rename 5 of the 6 code sites and miss the same one, `service.py:25` `small.title`; all five leave
the template alone, which is correct. In C9 all five rename the 2 real sites and leave the third alone, which
is correct because the call is invalid (8.1). In C6 and C7, "18" and "8" for pyrefly and jedi are the code sites
with the `__all__` string left in place; ty reaches 18 of 19 and 8 of 9 by the same omission. jedi's C5 cell is
"2 or 3" because its fragment counts "2 of 3 real sites" and does not state whether `broken.py:6`'s keyword
argument was renamed (see section 9).

**Latest versions (section 4):** pyrefly 1.4.0 raises its C5 cell from 2 to 4 (4.3); ty 0.0.89, basedpyright
1.40.2 and, by the C4 A/B, pyright leave every other cell in this table as it stands.

### 3.2 Navigation and consumption, C13 to C20

| Server | C13 implementations of `Port` | C14 implementations of `Drawable` | C15 definition | C16 definition through alias | C17 hover | C18 document symbols | C19 workspace symbols | C20 containment |
|---|---|---|---|---|---|---|---|---|
| pyright | `-32601 Unhandled method` | `-32601` | PASS, on the class | PASS, on `class Port` | PASS, signature + docstring (repo) | 12 of 12, 22 symbols; kinds: `kind` Variable, `label` Method, `__init__` Method, `DEFAULT_LIMIT` Constant | PASS, both, nothing opened | 3 of 3 |
| basedpyright | PASS: `StructuralPort`, `NominalPort`, plus the declaration | PASS: `InheritedDrawable`, plus the declaration | PASS | PASS | PASS, signature + full docstring (repo) | 12 of 12, 22 symbols; same kind deviations | PASS | 3 of 3 (last line `cached_load`) |
| ty | `-32601 Unknown request` | `-32601` | PASS | PASS | weak: decorator wrapper, `property`, class object; full signature + docstring on ordinary repo symbols | 12 of 12, 16 symbols; `kind` Field, `__init__` Constructor, `label` Method | PASS, both | 3 of 3 (last line `cached_load`, past-EOF `<module>`) |
| pyrefly | `null` (an empty answer, not `[]`, see 4.5) | `null`, same | PASS | PASS | PASS, text recorded (wrapper for `cached_load`) | 12 of 12; `kind`, `label`, `__init__` and `DEFAULT_LIMIT` kinds differ | partial: empty at the ready signal, duplicates once settled, substring match | 3 of 3 |
| jedi | `-32601 Method Not Found` | `-32601` | PASS | PASS | partial: `Widget` and `label` right, `cached_load` shows the wrapper | 12 of 12 plus 5 phantom entries reported as defined in `impl.py`; a property as Method, an instance attribute as Property | PASS, both | 1 of 3 (return line `draw`; decorator line and last line null) |

C20's protocol expectation for the last line was wrong; `cached_load` is the correct innermost symbol (8.3).
Four servers answered it, jedi answered null, and jedi's fragment attributes that null to `solidlsp`
refusing a blank line before any request reaches the server.

**Latest versions:** ty 0.0.89 answers C13 and C14 partially, where the table says `-32601`, and never returns
the structural implementation (4.2); pyrefly 1.4.0 answers `null` rather than `[]` at the class position and
only at a method position, fixes the C19 duplicates and corrects two of the C18 kinds (4.3); basedpyright's
column is identical at 1.40.2 (4.4).

### 3.3 Diagnostics and freshness, C21 and C22

| Server | C21 pull before open | C21 push after open | C22 freshness |
|---|---|---|---|
| pyright | `{"kind":"full","items":[]}` (no error) | 2 diagnostics, both severity 1, correct rules (`reportAssignmentType`, `reportAttributeAccessIssue`); also pushed `Import "pytest" could not be resolved` from the initialize option | PASS, live saw the new site, restart changed nothing |
| basedpyright | `{"kind":"full","items":[]}`, no push | 4 diagnostics: the 2 errors plus `reportUnusedCallResult` and `reportUnknownMemberType` as warnings; messages in French with `codeDescription` links | PASS (with `workspace/didChangeWatchedFiles`), restart byte-identical |
| ty | `-32602 Document <uri> is not open in the session` (at 0.0.25; 0.0.89 answers a silent empty report, 4.2) | 2 diagnostics: `invalid-assignment`, `unresolved-attribute` | PASS, restart changes nothing |
| pyrefly | `{"items":[],"kind":"full"}` | `[]`, 0 of 2: with no `[tool.pyrefly]` section the server runs the `basic` preset (see 5.6) | PASS through both `didChange` and `didChangeWatchedFiles` |
| jedi | `-32601 Method Not Found` | `{"diagnostics":[],"version":1}`; the channel is syntax-only (a control with `def oops(:` did report `SyntaxError`) | PASS, live and durable |

### 3.4 Cost on the fixture, C23

| Server | Startup to first answer | Memory, process tree | definition | references | rename | document symbols |
|---|---|---|---|---|---|---|
| pyright | 0.341 s (initialize 0.159 s; `Found 8 source files` at 0.26 s) | 175 MiB after the first answer, 206 MiB after the sequence | 0.2 ms | 0.4 ms | 0.5 ms | 0.2 ms |
| basedpyright | 0.31 s (initialize 0.159 s; analysis complete 0.23 to 0.24 s; then 0.072 s) | 213.8 MiB (uvx 39.7 + python 15.9 + node 158.2) | 0.2 ms | 0.4 ms | 0.4 ms | 0.2 ms |
| ty | 0.023 s (initialize 18 ms; first answer 5.2 ms later) | 84 MiB (uvx 38 + ty 46) | 0.1 ms | 0.1 ms | 0.1 ms | 0.2 ms |
| pyrefly | 0.036 to 0.058 s to the ready signal, first correct answer 0.109 s | 100 MiB (pyrefly 64 + uvx 37) | 0.16 ms | 0.28 ms | 0.22 ms | 0.29 ms |
| jedi | 0.34 s (0.265 s start + 0.075 s), no index | 55.5 MiB server, plus ~27.8 MiB helper and 45 MiB uvx launcher | 0.4 ms | 8.3 ms | 10.6 ms | 6.9 ms |

Medians of 5, measured with `time.monotonic()` around the request on an already-initialised session; the
fragments' drivers differ, so sub-millisecond differences between servers are not properties of the servers
(both the pyright and the basedpyright fragments warn about this). Serena adds a one-off 2 s wait before the
first definition or references request of a session with pyright, which is not in these numbers. pyright's
0.341 s and basedpyright's 0.31 s both include the `uvx` shim (~0.15 s) from a warm cache.

**Latest versions:** ty 0.0.89 initializes in 14 ms with an 80 MiB tree; basedpyright 1.40.2 reads 228.8 MiB
tree with every median up by 0.1 to 0.3 ms (4.2, 4.4).

### 3.5 Repository, C24

Configuration needed, index time, memory, latency on a named real symbol, diagnostics, coverage.

| Server | Configuration | Index / start | Memory | Latency on a named real symbol | Diagnostics on real files | Whole tree or opened files |
|---|---|---|---|---|---|---|
| pyright | the committed `[tool.pyright] venvPath = "." venv = ".venv"`; the clone needed a `.venv`, materialised as a symlink farm to the original with the 8 editable `.pth` rewritten | 335 files in 0.26 s; first answer 0.353 s | 278 MiB, 481 MiB after the sequence | def 0.3 ms, refs 27.7 ms, rename 26.8 ms (13 sites, 7 files), docsym 0.5 ms | none, on 4 opened real files | whole tree indexed, opened files diagnosed only |
| basedpyright | `uv sync --dev` in the clone (1.0 s), the committed block as is (it is redundant: basedpyright finds `./.venv` alone) | analysis complete 0.22 s, first answer 0.43 s, 0.65 s total | 438 to 452 MiB | on the port's `record_observation`: def 0.2 ms, refs 4.2 ms, rename 3.2 ms (2 sites) | 0 errors on 4 opened real files; 0 / 26 / 21 / 4 warnings per file (CLI on the same four: `0 errors, 23 warnings`, exit 1) | whole tree symbols, opened-file diagnostics (workspace mode only over `didChangeConfiguration`) |
| ty | a `ty.toml` at the copy root: `[environment] python` plus `extra-paths` for the 8 members (verbatim in 6) | initialize 20 ms, cold whole-tree `workspace/symbol` 11 ms over 333 `.py` | 90 MiB after the scan, 200 MiB after all requests | def 0.1 ms, refs 0.8 ms, rename 1.0 ms, docsym 0.2 ms, hover 0.1 ms, ws/symbol 0.6 ms | only for files opened in the session (6 URIs after opening 6 of 333 and waiting 25 s) | whole tree indexed for symbols and references; `textDocument/*` refuses unopened files |
| pyrefly | `[tool.pyrefly] search-path` (8 members) plus `python-interpreter-path` = the real `.venv/bin/python`, plus `preset = "default"` (a no-op once a config exists) | ready ~30 ms | 179 MiB (pyrefly 142 + uvx 37) | def 0.27 ms, refs 1.64 ms, rename 1.80 ms, docsym 0.48 ms (13 edits in 7 files) | publishes for the whole tree (228 files in the bare stage), because Serena's `workspace/configuration` reply sets `diagnosticMode: workspace` | whole tree, indexed and diagnosed |
| jedi | `initializationOptions` `{"workspace": {"environmentPath": ..., "extraPaths": [...]}}`; base options include `symbols: {ignoreFolders: [...], maxSymbols: 0}` | start 0.286 to 0.289 s; first tree walk 0.16 s, then 0.04 s | 90.4 MiB after the first walk, 114.1 MiB at the end, plus ~30 MiB helper | def 1.2 ms, refs 31.5 ms (13 sites, 7 files), rename 90.6 ms, docsym 10.5 ms | one `publishDiagnostics` with an empty array; pull `-32601` | whole tree, walked on demand, no index |

Repository file counts differ between fragments for a benign reason: 335 is every `.py` outside `.venv` and
`.git`, 333 is the number under `packages/` and the number the gate's scope holds. Re-checked for this merge:
`find . -name '*.py' -not -path './.venv/*' -not -path './.git/*' | wc -l` gives 335, `find packages -name
'*.py' | wc -l` gives 333, the two extra being `conftest.py` and `vulture_whitelist.py` at the repository root.
basedpyright's re-measurement reads 336 files because its sessions write one never-opened probe file into the
copy (4.4).

**Latest versions:** ty 0.0.89 resolves the same tree with the same `ty.toml` (42 diagnostics against 68; the
implementation request returns 1 result, the Protocol itself, where the table says `-32601`) (4.2); pyrefly
1.4.0 resolves it with the one-line interpreter path, at +58 MiB (4.3); basedpyright 1.40.2 is unchanged site
for site, 477.2 MiB tree (4.4).

### Evidence lines, per case

Command shapes: pyright `python3 -I cases_fixture.py` then `results_fixture.json`; basedpyright
`python lspbench.py fixture` then `results-fixture.json`; ty `cases_fixture.py` then `results_fixture.json`
and `logs/run_all.txt`; pyrefly `python run_a.py` then `run_a.json`; jedi `run_fixture.py` then
`apply_renames.py`. The decisive line per server and per case:

- **C1** (6 sites). pyright, basedpyright, ty: `C1.sites` = `[ports.py:8, service.py:25]` and nothing in `impl.py`; basedpyright adds `references_Port_render` with `includeDeclaration=true` = the same two, "i.e. the rename is exactly the references set". pyrefly: `references_includeDeclaration_Port.render` = 5 sites, `impl.py:15:8` present and `impl.py:10:8` absent. jedi: `apply_renames.py C1` shows `lspfix/service.py -alias.render +alias.paint` and no `impl.py` entry.
- **C2** (3). pyright: `C2.sites` = `[ports.py:13, service.py:23]`, and `refs_Drawable_draw` misses the override too. basedpyright: `C2.site_count = 2`. ty: edits `ports.py:13:8`, `service.py:23:13`. pyrefly: `run_a.json` C2 = `impl.py:32:8`, `ports.py:12:8`, `service.py:22:13`. jedi: `apply_renames.py C2` then instantiating `InheritedDrawable` raises `TypeError: Can't instantiate abstract class InheritedDrawable without an implementation for abstract method 'sketch'`.
- **C3** (3). pyright: `refs_Sink_emit` = `[ports.py:18]`, and with `includeDeclaration=false` = `[]`. basedpyright: `references_NominalSink_emit` = `[impl.py:38:9, service.py:21:10]` while `references_Sink_emit` = `[ports.py:18:9]`. ty: one edit, `ports.py:18:8`. pyrefly: `impl.py:37:8`, `ports.py:17:8`, `service.py:20:9`. jedi: one file in `documentChanges`.
- **C4** (4). pyright: reproduced on a fresh minimal project, both 1.1.403 and 1.1.414: `rename_from_base` = lines 2 and 12 only, and `rename_from_override` returns the override alone; `definition_of_upper_call` does land on `Upper.handle`. basedpyright: `rename_Upper_handle_from_override` = 1 site. ty: the raw `changes` response holds `base.py:2` and `service.py:22` only. pyrefly: `base.py:1:8`, `base.py:6:8`, `base.py:11:8`, `service.py:21:12`, stable in a fresh session. jedi: after applying, `Upper.__dict__` still has `handle` while `Handler` has `process`.
- **C5** (4). pyright: `C5.sites` = the 4 occurrences, `widget.replace(size=4)` unchanged. basedpyright: same 4. ty: `broken.py:6:26`, `service.py:26:54`, `widget.py:10:26`, `widget.py:11:28`. pyrefly: 2 edits, both in `widget.py`; `C5 definition of the limit kwarg at the call site` returns `widget.py:9:26` while `C5 references at build's limit parameter` never lists `service.py:25`; the control module shows a same-file `plain(alpha=2)` is renamed and a cross-file one is not. jedi: `apply_renames.py C5` shows the two `widget.py` edits; the fragment does not state whether `broken.py:6` was included.
- **C6** (19). pyright: 19 sites including `__init__.py:4` (`"Widget"` inside `__all__`). basedpyright: `C6.site_count = 19`, `lspfix/__init__.py:4:21->Card`. ty: 18 edits, `__init__.py:4` absent. pyrefly: 18 edits, `__init__.py:4` absent, described as correctly left alone. jedi: 24 edits in 7 files, 18 renamed lines, `__init__.py` has 2 edits both on line 1.
- **C7** (9). pyright: 9 sites, `STRING_PORT` and every `WidgetPort` untouched. basedpyright: `C7.sites` = 9. ty: 8 edits, no edit on `service.py:8`, none on any `WidgetPort`. pyrefly: 8 sites, `service.py:4:25` is the `Port` token, not `WidgetPort`. jedi: 9 edits in 5 files, 8 renamed lines, `alias: WidgetPort` untouched.
- **C8** (6 code sites plus 2 template). pyright: 5 sites, `service.py:25` missing; `refs_Widget_title` identical. basedpyright: `references_small_title` (asked at `service.py:24:42`) = `[]`. ty: 5 edits; `small` is `Unknown` because `Widget.replace` does not exist. pyrefly: `C8 hover of small.title` = `title: Unknown`, `C8 definition of small.title` = `[]`. jedi: 5 renamed lines, no `service.py` entry; missing site is `service.py:25`.
- **C9** (2 real). All five: edits at `widget.py` and `broken.py` only, nothing at `service.py:24`. pyright: `refs_Widget_size` = `[broken.py:7, widget.py:7]`. pyrefly: `C9 hover of the size kwarg` = `null`. jedi: 2 files only. ty: `unresolved-attribute: Object of type Widget has no attribute replace` at `service.py:24`.
- **C10** (5). All five include the two import lines and leave `@functools.cache` untouched: pyright `C10.sites` = 5; basedpyright 5; ty 5 edits; pyrefly `impl.py:46:4`, `service.py:25:18`, `service.py:2:68`, `tests:18:11`, `tests:3:40`; jedi 5 renamed lines in 8 edits.
- **C11** (3). All five: `impl.py`, `service.py:3`, `service.py:25`, and no edit on either string. pyright `C11.sites`; pyrefly leaves `service.py:8` and `service.py:29`; jedi leaves `service.py:9` and `service.py:30`.
- **C12** (5). pyright, basedpyright, ty, jedi: 1 site, the fixture definition only. jedi applied it and ran pytest: `2 errors` (`fixture 'widget' not found`). pyrefly: 3 edits (definition plus the two parameters), missing both body uses, which yields `def test_render(a_widget: Widget)` with a body calling `widget`; its control shows a local variable's read IS indexed, so the fixture parameter binding is the specific gap.
- **C13, C14**. pyright: `{"code":-32601,"message":"Unhandled method textDocument/implementation"}` and no `implementationProvider` in the capabilities. ty: `{"code": -32601, "message": "Unknown request: textDocument/implementation"}`. jedi: `Method Not Found: textDocument/implementation (-32601)`. pyrefly: `null` (the baseline fragment wrote `[]`; the transcript holds `null`, see 4.5) from a server that advertises `implementationProvider: true`. basedpyright: `impl.py:10`, `impl.py:15`, plus `ports.py:7`; at the alias annotation `service.py:19:12` it returns none.
- **C15, C16**. All five land on the class, never on a re-export: pyright `widget.py:5` char 6; basedpyright also from the import line; ty `targetSelectionRange` lines 4 to 7 (decorator-inclusive); pyrefly `lspfix/widget.py:4:6`; jedi `widget.py` range 4:6-4:12. C16: `ports.py:7` (pyright, basedpyright), `ports.py:7:6` (ty), `lspfix/ports.py:6:6` (pyrefly), `ports.py` 6:6-6:10 (jedi).
- **C17**. pyright `(function) def cached_load(name: str) -> WidgetName`, `(property) label: (self: Self@InheritedDrawable) -> str`, `(class) Widget`; on the repository, the signature fence, a `---` separator and the whole class docstring. basedpyright the same three, plus at the call site `(function) cached_load: _lru_cache_wrapper[WidgetName]`. ty: `_lru_cache_wrapper[str]`, `property`, `<class 'Widget'>`; on the repository a normal method returns its full signature plus docstring. pyrefly: `` ```python\n(function) cached_load: _lru_cache_wrapper[str]\n``` `` plus links. jedi: `cached_load` returns `def _lru_cache_wrapper(*args: Hashable, **kwargs: Hashable) -> _T_co`, `label` returns `def label()`, `Widget` returns `class Widget(title: str, size: int)`.
- **C18**. Only differences of kind, all 12 symbols present everywhere. pyright and basedpyright: `kind` = Variable (13), `label` = Method (6), `__init__` = Method (6), `DEFAULT_LIMIT` = Constant (14), `WidgetName` = Variable, `cached_load` = Function. ty: `kind` Field, `__init__` Constructor, `label` Method. pyrefly: `kind` Variable, `label` Method, `__init__` Method, `DEFAULT_LIMIT` Variable. jedi: `kind` and `_label` reported as Property (7), `label` as Method (6), plus 5 phantom entries on the import lines (`functools`, `Drawable`, `Port`, `Sink`, `Widget`) reported as defined in `impl.py`.
- **C19**. pyright: `workspace_symbol_Lower` and `workspace_symbol_StructuralPort` with `opened_files_session_b` = `[]`. basedpyright: `Lower -> base.py:11`, `StructuralPort -> impl.py:10`, no `didOpen` at all, and an empty query answers nothing. ty: both found with 0 ms and nothing opened. pyrefly: `immediately` = `{"Lower": [], "StructuralPort": []}`, `after_2s` = 3 copies of `StructuralPort`, growing by one per later file open; a `Widget` query also matches `WidgetName` and `WidgetPort`. jedi: both, `base.py` 10:6 and `impl.py` 9:6, `server_notifications == []`.
- **C20**. pyright `{"last_line_47":"cached_load","decorator_line_45":"cached_load","return_line_33":"draw"}`. basedpyright the same three, calling the last-line answer a stated deviation from the protocol. ty: `cached_load` for the last line and the decorator, `InheritedDrawable.draw` for the return, `<module>` one line past EOF. pyrefly: `cached_load`, `cached_load`, `InheritedDrawable.draw`, computed with Serena's own algorithm. jedi: `last_line_of_impl` null (solidlsp logs `Passing empty lines to request_container_symbol is currently not supported`), `decorator_line` null (the document symbol spans lines 47 to 48, so the decorator on line 46 is outside it), `return_self_label` = `draw`.
- **C21**. pyright `C21_pull_before_open` = `{"kind":"full","items":[]}`; `C21_push_after_open` = 2 items, severity 1, the two constructed errors. basedpyright: pull before open `{"kind": "full", "resultId": "2", "items": []}`, then 4 items after `didOpen`. ty: pull `{"code": -32602, "message": "Document file:///.../lspfix/broken.py is not open in the session"}`, then `invalid-assignment` and `unresolved-attribute` pushed. pyrefly: `run_h.py` flips `[]` to `['bad-assignment', 'missing-attribute']` when an empty `[tool.pyrefly]` (or a `[tool.mypy]` section) is added; CLI cross-check `--preset basic` prints `INFO 0 errors` while `--preset default` prints the two. jedi: one `publishDiagnostics` with `{"diagnostics": [], "version": 1}`; the control with a syntax error reports it.
- **C22**. pyright `live_sees_new_site: true`, `restart_changed_answer: false`. basedpyright `before_append` 2 sites, `live_after_append` 3, `after_restart` identical. ty 1 site, 2 sites after a `didChange`, 2 after a restart. pyrefly 2 to 3 through both `didChange` and `didChangeWatchedFiles`, restart unchanged. jedi 2 to 3, same after restart.
- **C23, C24**: the tables in 3.4 and 3.5; artifacts `results_final.json`, `results-repo-v4.json`, `logs/results_repo_tytoml.json`, `run_repo.py`, `run_g.py`, `probe_latency.py`, `probe_real_repo3.py`, `scope_check.py`.

Falsifiers, as the protocol demanded: the axis I fragments supply one per criterion (an implementation query
returning a location list for C13/C14; a third edit at `service.py:25` for C5; a `service.py:24` entry for C9;
a diagnostic naming `rows: int = "many"` for C21; an answer in `impl.py` for C1, and so on). Two are weak and
are called out rather than repeated as if they were checks: jedi's C20 nulls mix a server property (the
document symbol range excludes the decorator) with a client artefact (`solidlsp` refusing a blank line), and
jedi's C5 count does not say whether `broken.py:6` was renamed.

## 4. The latest releases: three re-measurements (2026-10-17)

The operator's rule is that no server is dropped on a stale version, so three of the five were re-measured at
their latest release the day after the bench, with the same protocol, the same cases and the same frozen
fixture. Sections 3 and 5 to 10 report the pinned versions; this section says, per server, what the latest
release changes and what it does not. The three fragments:

| Fragment | Server | Version | Fixture revision | Repository revision |
|---|---|---|---|---|
| `/tmp/lsp-bench/out/ty-latest.md` | ty | **0.0.89** | `b050f86c735ac266f5c556054c21f4e92165d351` | `7f74b555` (the commit that added this report; `git diff --stat fd9d681..7f74b55` is one added Markdown file, so the code tree is the baseline's) |
| `/tmp/lsp-bench/out/pyrefly-latest.md` | pyrefly | **1.4.0** | `b050f86c735ac266f5c556054c21f4e92165d351` | `7f74b555`, same one-file diff check |
| `/tmp/lsp-bench/out/basedpyright-latest.md` | basedpyright | **1.40.2** | `b050f86c735ac266f5c556054c21f4e92165d351` | checked out at `fd9d6814`, the baseline's revision, for comparability |

All three report the fixture revision `b050f86c735ac266f5c556054c21f4e92165d351` and a clean copy at the end of
the runs, so the comparability check of section 1 holds for the re-measurements too. **pyright and jedi were
not re-measured at their latest releases.** The only latest-version datapoint for pyright is the original
fragment's A/B on the minimal override case (identical results on 1.1.403 and 1.1.414), and jedi has none; for
those two this report cannot say what the latest release changes.

Summary, per server:

| Server | Latest measured | What the latest changes | What it does not change |
|---|---|---|---|
| ty | 0.0.89 (pin 0.0.25) | `textDocument/implementation` exists (nominal subclasses only); the `-32602` gate on unopened documents is gone; pull diagnostics on an unopened file became a silent empty report | all twelve renames byte-identical; C8, C9, C12 verdicts; C1 to C4; the import-line classification; `workspace/diagnostic` and `typeHierarchy/*` still broken |
| pyrefly | 1.4.0 (pin 1.2.0) | the cross-module keyword argument is renamed (C5 2/4 to 4/4); workspace-symbol duplicates gone; two C18 kinds corrected; one-line repository configuration | the rename equals the reference index, so C1, C8, C12 gaps stay; implementations remain nominal-only; the `basic` preset trap; the empty answer at the ready signal |
| basedpyright | 1.40.2 (pin 1.39.9) | class hover now renders the constructor and drops the `(class)` prefix; node memory +11% | every case verdict, site for site, including the whole repository picture; the diagnostics channels; the rename gap |
| pyright | not re-measured (pin 1.1.403; 1.1.414 exists) | unknown beyond the C4 A/B | unknown |
| jedi | not re-measured (0.47.0) | unknown | unknown |

### 4.1 The pins, and how a project overrides one

Every uvx-launched server carries its pin as `--from <package>==<version>` in the launch command, built by
`solidlsp/dependency_provider.py`. The pin lives in the server module and the override key is declared next to
it, verbatim from the installed Serena 2.0:

```
$ grep -rn "version_setting_key" ~/.local/share/uv/tools/serena-agent/lib/python3.13/site-packages/solidlsp/language_servers/*.py
language_servers/pyright_server.py:54:            version_setting_key="pyright_version",
language_servers/basedpyright_server.py:50:            version_setting_key="basedpyright_version",
language_servers/ty_server.py:49:            version_setting_key="ty_version",
language_servers/pyrefly_server.py:136:            version_setting_key="pyrefly_version",
```

and the read is one line (`dependency_provider.py:281`):
`version = self._custom_settings.get(self._version_setting_key, self._default_version)`, which feeds
`--from {package}=={version}` (`_build_uvx_base_command`). So the setting is
`ls_specific_settings: {<serena id>: {<key>: "<version>"}}`, in the project's `.serena/project.yml` or the
global `~/.serena/serena_config.yml`.

| Serena id | Package | Pin in Serena 2.0 | Constant | Override key | Latest measured |
|---|---|---|---|---|---|
| `python` | pyright | 1.1.403 | `PYRIGHT_VERSION` | `pyright_version` | not re-measured (1.1.414 is the current release) |
| `python_basedpyright` | basedpyright | 1.39.9 (based on pyright 1.1.411) | `BASEDPYRIGHT_VERSION` | `basedpyright_version` | 1.40.2 (based on pyright 1.1.414) |
| `python_ty` | ty | 0.0.25 | `TY_VERSION` | `ty_version` | 0.0.89, which is also `uvx ty@latest` |
| `python_pyrefly` | pyrefly | 1.2.0 | `PYREFLY_VERSION` | `pyrefly_version` | 1.4.0, PyPI's latest on 2026-10-15 |
| `python_jedi` | jedi-language-server | none: no dependency provider, the bare `jedi-language-server` command from `PATH` | n/a | none | not re-measured (0.47.0) |

The override was proven at the provider level by building the launch command the way Serena does
(`/home/geoffrey/.claude/jobs/c2b09c03/tmp/pin_check.py`, `pin_check2.py`):

```
no ls_specific_settings             -> ['/usr/bin/uvx', '-p', '3.13', '--from', 'ty==0.0.25', 'ty', 'server']
python_ty.ty_version = 0.0.89       -> ['/usr/bin/uvx', '-p', '3.13', '--from', 'ty==0.0.89', 'ty', 'server']
python_ty.ls_path = /usr/bin/true   -> ['/usr/bin/true', 'server']
```

and through the real lookup Serena performs:
`get_ls_specific_settings(LanguageServerId.PYTHON_TY).get("ty_version", "0.0.25")` returns `"0.0.89"`. All
three re-measurements then used the mechanism for real: basedpyright's session was built with
`ls_specific_settings={"python_basedpyright": {"basedpyright_version": "1.40.2"}}`, pyrefly's with
`{"python_pyrefly": {"pyrefly_version": "1.4.0"}}`, ty's by re-pointing its launch command at the pinned
version. So the mechanism is proven by use for three of the four uvx servers, and by the same code path
(`version_setting_key` present, same provider class) for pyright.

Caveats a decision has to carry:

- **The project-level form needs a trusted project.** `serena/project.py:669-676` merges the project's
  `ls_specific_settings` over the global ones only `if self.is_trusted()`, and warns otherwise. This machine is
  trusted (`trusted_project_path_patterns: ['**']` in `~/.serena/serena_config.yml`), and the global file
  already uses the mechanism for another language, so the pattern is proven here.
- **The repository's own `ls_specific_settings` is empty today**, so the override is a two-line edit to
  `.serena/project.yml`, not a change to Serena.
- **`install_dependencies()` installs the same resolved version** (`uv tool install -p 3.13 ty==0.0.89`), so a
  client that pre-installs dependencies is coherent with the override.
- **`ls_path` bypasses uv entirely**: the configured binary is launched with the server's own extra arguments
  appended, for a project that wants a single shared artefact.
- **An unavailable pin fails loudly at the process level, and the LSP-level half is unproven.** The provider
  pins with an exact `--from <package>==<version>` (`_build_uvx_base_command` in the installed
  `dependency_provider.py`) and holds no fallback branch, so a version that cannot be resolved makes uvx refuse:
  a client launched with `["/usr/bin/uvx","-p","3.13","--from","ty==9.9.9","ty","server"]` on the frozen
  fixture got `error: No solution found when resolving tool dependencies` and the cause
  `Because there is no version of ty==9.9.9 and you require ty==9.9.9, we can conclude that your requirements
  are unsatisfiable.`, with process exit code 1, re-checked 2 s later, and no fallback to any other ty version
  (`ty==0.0.999` behaves the same, checked while merging this section). `install_dependencies()` is the same
  shape: `RuntimeError("Installation of {package}=={version} failed: ...")` on a nonzero exit. **The
  qualification**: it is loud at the process level but not at the LSP level, since no JSON-RPC frame is ever
  sent, so that client's `initialize` request **timed out after 90 s** rather than returning an activation
  error; solidlsp's behaviour in that case was not tested, so whether Serena surfaces a timeout or an error is
  open. A client that does not watch the child process sees a hang, not a failure. For contrast, a launch
  command that cannot be executed at all terminates visibly: the jedi fragment saw `START FAILED:
  SolidLSPException ... (caused by LanguageServerTerminatedException: Language server stdout read process
  terminated unexpectedly)`.
- **jedi is outside this mechanism**: no pin, no provider, so nothing to override and no version to drift.
- **A Serena-side landmine, harmless today**: `LanguageServerId.PYTHON_TY.supports_implementation_request()`
  returns `False` because `TyLanguageServer` does not override the base, and nothing in `serena/` reads the
  flag today (`FindImplementationsTool` issues the request unconditionally). If Serena ever honours it, ty is
  excluded from implementation lookups whatever version it runs.

### 4.2 ty 0.0.89: the gate is gone, the rename is not

Three behaviours move, everything else in C1 to C24 is byte-identical to 0.0.25.

**The `-32602` gate is gone, and it was a bug.** On 0.0.25, every `textDocument/*` request for a document that
had never been `didOpen`-ed answered an error (16 of the 18 probed methods with
`-32602 Document <uri> is not open in the session`, the 2 unimplemented hierarchy methods with `-32601`). On
0.0.89, 17 of the 18 answer with real results, and the single exception is `textDocument/typeHierarchy/supertypes`,
which answers `-32601` because the method is unimplemented, not because the document is closed. All 18 answers
after `didOpen` are byte-identical to the 18 before it, checked pairwise. The fix is release
0.0.84 (2026-09-24), "Support LSP requests against closed documents"; the two numbers come from two places and
both are real: the release note carries the PR
(`grep -n "closed documents" /tmp/lsp-bench/checker/ty-changelog.md` gives line 294 under `## 0.0.84`, linking
`astral-sh/ruff#28595`, a ruff PR), and the issue is named in that PR's body
(`gh api repos/astral-sh/ruff/pulls/28595 --jq .body` contains `Fixes https://github.com/astral-sh/ty/issues/3624.`),
astral-sh/ty#3624 being titled verbatim "LSP requests are only fulfilled for open documents ⇒ non-compliant
with LSP spec" (`gh api repos/astral-sh/ty/issues/3624`), which is exactly the defect the 0.0.25 fragment
documents. The two ty fragments are the two ends of one upstream bug.

**Pull diagnostics on an unopened file changed from a loud error to a silent wrong answer.** The same change
that removed the gate removed the refusal on `textDocument/diagnostic`: on 0.0.89 it returns
`{"items": [], "kind": "full"}`, with no `resultId`, for a file that has two errors, and the same empty report
for a file in a tree where six other files are open. On 0.0.25 the call was refused loudly. For any client that
trusts the report, the new behaviour is worse than the old one: it reads as "no problems" instead of "not
open". This is the one regression the re-measurement found.

**`textDocument/implementation` exists (0.0.64, 2026-07-27) and answers nominal subclasses only.** The
capability is advertised and the request is answered; the query is at the class or member position, and the
queried symbol is always included in its own answer, so a caller has to filter it out:

| Query | Result on 0.0.89 |
|---|---|
| `Port` (the Protocol) | `ports.py:7` (itself) and `impl.py:15` (`NominalPort`); `StructuralPort` is **not** returned |
| `Port.render` (the member) | `ports.py:8` (itself) and `impl.py:16` (`NominalPort.render`) |
| `NominalPort` (already an implementation) | `impl.py:15` (itself), no subtypes |
| `StructuralPort` (structural: never names `Port`) | `impl.py:10` (itself), nothing else |
| `Drawable`, `Sink` (ABCs) | the ABC itself plus the single nominal subclass |

On this repository the consequence is exact: `textDocument/implementation` on `CatalogRepository` returns the
**Protocol itself** and not `SqliteCatalogRepository`, whose docstring says it implements the port and which
never names it as a base. The provider is real and it does not cover this project's idiom; C13 and C14 move
from "not supported" to "answered, partially".

**Everything else is unchanged**, including all twelve renames, edit for edit: C1 2 of 6, C2 2 of 3, C3 1 of 3,
C4 2 of 4 (still a silent dispatch change), C5 4 of 4, C6 18 of 19 (the `__all__` string still missed), C7 8 of
9, C8 5 of 6 (`small.title` still unreachable), C9 2 of 2 valid, C10 5 of 5, C11 3 of 3, C12 1 of 5. Two
smaller moves are worth recording: `references` on a module-level constant now honours `includeDeclaration`
(`DEFAULT_LIMIT` with `false` returns 1 site instead of 2, consistent with functions), and 0.0.89 pushes new
severity-4 hints with **no `code`** (`Code is always unreachable`, `` `x` is unused ``), which breaks a client
that keys diagnostics on `code` (it broke the fragment's own script). The pytest-fixture work landed
(0.0.75/0.0.76: definition of a fixture parameter navigates to the fixture, references of the fixture definition
return 4 sites) but **rename does not use it**: renaming the fixture still leaves the four parameter
occurrences, so C12 stays a fail under Serena either way, and only when `pytest` resolves at all (the frozen
fixture has no environment, so it keeps the old 1-of-5 answer). `workspace/diagnostic` is still advertised
(`workspaceDiagnostics: true`, `workDoneProgress: true`) and still never answered: no response and no
`$/progress` frame after **300 s** on a ten-file fixture, and `{}` still rejected at parse time. The repository
picture: with the same `ty.toml`, the CLI reports 42 diagnostics against the baseline's 68 (one vanished
`invalid-argument-type` on `policy.py:208` verified as a real false positive; the other 25 not audited), the
rename of `CatalogRepository` is still 13 edits in 6 files, references still 6 sites, and pull diagnostics on a
not-open real file now answer the empty report instead of the old error. Costs are flat to slightly better
(initialize 14 ms against 18, fixture tree 80 MiB against 84, medians 0.2 / 0.2 / 0.1 / 0.1 / 0.1 ms); the
repository tree reads 127 MiB against 90, which the fragment itself flags as larger than the version can
explain and not repeated.

### 4.3 pyrefly 1.4.0: the keyword argument is fixed, the shape is not

**Fixed: the cross-module keyword argument.** C5 goes from 2 of 4 word-boundary sites to **4 of 4**:
`service.py:25:54` and `broken.py:5:26` join the parameter and its body read. The change is pinned to the
source, not guessed: at the 1.4.0 tag the reference path has a `SymbolKind::Parameter` branch that fetches each
candidate's AST to resolve the callee ("Keyword argument references require each candidate's AST and bindings
to resolve the callee and refine the argument back to this parameter"), and the same function at the 1.2.0 tag
has no such branch.

**Fixed: the workspace-symbol duplicates.** C19's second defect is gone: one result per symbol, no growth on
file open (was 3, 3, 4, 5, 6). The first defect is not: the answer is still empty at the instant Serena
declares the server ready, with a wider window than before (correct at +62.4 ms against 1.2.0's +41.6 ms, from
a ready signal that arrives 14 ms earlier, so spawn to first correct answer is about the same). Substring
matching is unchanged (`Widget` also returns `WidgetName` and `WidgetPort`).

**Fixed: two of the four C18 kind deviations.** `DEFAULT_LIMIT` is now `14 Constant` (was 13 Variable) and
`InheritedDrawable.kind` is now `8 Field` (was 13 Variable); `label` and `__init__` are still reported as
Method.

**Not fixed, and not fixable by configuration: implementations are nominal-only by construction.** C13 and C14
are still empty at the class position (and the baseline fragment's `[]` is wrong: the transcript holds `null`
in both versions, see 4.5). New measurement: the request works at a **method** position and returns the
nominal override only (`Port.render` gives `NominalPort.render`; `Drawable.draw` gives `InheritedDrawable.draw`),
and never the structural one. The source says why: `find_child_implementations_impl` reads a
`parent_methods_map` populated from `for ancestor in mro.ancestors(...)`, the nominal MRO, with no structural
pass and no setting that adds one, and the map is keyed by method declaration ranges, which is why a class
position answers nothing. Likewise `textDocument/rename` is `async_find_references_helper` with
`textual_only(true)`, so rename is the reference index verbatim and inherits every reference gap (C1's
`StructuralPort.render`, C8's `small.title`, C12's fixture body uses), as well as the C5 fix.

**One-line repository configuration, and the eight `search-path` entries were a bench artefact.**
`python-interpreter-path` pointing at the workspace's own `.venv` already gave 13 references and 13 rename
edits across 7 files on 1.2.0 (stage (f), a venv created inside the copy); the baseline's eight-entry
`search-path` was needed only because it pointed a **copy** at the **original** repository's venv (stage (e)),
where the editable `.pth` files resolve outside the copy. On the real tree, where venv and workspace are the
same tree, the interpreter line alone resolves all eight members. The price of dropping `search-path` is
**+58 MiB** resident on this tree (201 MiB against 144 MiB, both flat over 30 s), because the members become
first-party files to solve. 1.4.0 also stops refusing renames in that configuration: 1.2.0 answered stage (e)
with `definition = null`, `references = []` and `Third-party symbols cannot be renamed (-32600)`, and returned
14 to 15 duplicate `SqliteCatalogRepository` symbols; 1.4.0 answers all three and returns 1 (the release note:
"uv workspace members are now type checked").

**Other measured moves**: `typeHierarchy/subtypes` now answers on a Protocol class (`Port`: `[]` to
`["NominalPort"]`); cross-file attribute **assignment** is renamed (a control class: 5 sites to 6, the extra
one being `h.total = 9` in the consuming module); `[tool.basedpyright]` is now read as a preset source;
`cached_load`'s hover prints the qualified `functools._lru_cache_wrapper[str]`; startup is faster (ready-signal
median 16.4 ms against 29.7 ms measured the same way). **Unchanged**: C1 5 of 6, C6/C7 complete on code sites,
C8 5 of 6, C11, C12 3 of 5, C15 to C17, C20, C22, and C21's 0 of 2 with the `basic` preset trap intact (the
presets were re-confirmed one variable at a time: no section `[]`, empty section both errors, `default` both,
`basic` `[]`, `strict` both, `all` both plus `unused-call-result`; this repository carries `[tool.mypy]` and
`[tool.pyright]`, so it was never silent).

**`--indexing-mode lazy-blocking`**, which Serena can pass through `ls_specific_settings.python_pyrefly.indexing_mode`,
removes the empty-at-ready window: the first request builds the index inside itself, so it blocks (59 to 60 ms
on the fixture, 263.9 ms against 105.6 ms for the first repository definition) and returns a correct answer
instead of a plausible empty one. No case changes its answer under it; the fixture pays about +20 MiB resident,
the repository pays no memory penalty.

### 4.4 basedpyright 1.40.2: nothing moves, and the diagnostics question is answered

**Site for site, the verdicts are identical to 1.39.9.** C1 to C8 and C10 to C12 return byte-identical rename
sets; C13, C14, C15, C16, C18, C19, C20, C21 and C22 are identical; the capabilities and initialize parameters
are identical; C5, C6 and C7 still cover the full word-boundary sets (4, 19 and 9 of 10). At the repository
level the picture is unchanged too: implementation of `CatalogRepository` returns the adapter and the test
double; renaming the port's `record_observation` returns **2 sites** while the adapter's own method returns
**71 sites across 9 files**. The known rename gap is a repository-level fact, not a version artefact.

**The one behaviour change: class hover.** `Widget` returns `class Widget(\n    title: str,\n    size: int\n)`
where 1.39.9 returned `(class) Widget`, and `StructuralPort` returns `class StructuralPort()`. Mechanism
located in the shipped bundle (the helper renamed from `_addInitOrNewMethodInsteadIfCallNode` to
`_addConstructorSignatureAndDocumentation`, now called with `includeUncalled = true`), and announced in **no**
release note of the range: it arrives inside the merged pyright 1.1.411 to 1.1.414 releases. Nothing in the 24
cases consumes hover text, so no verdict moves; a tool that parses hover text would see a different shape.

**The baseline's `diagnosticMode` anomaly is explained, and its finding is sharper.** The baseline recorded
that `diagnosticMode: "workspace"` in a `pyrightconfig.json` did not take effect and that it could not
establish why. It did not take effect because `diagnosticMode` is a **language-server setting**, parsed only
from the settings a client sends and never from the config file; 1.40.2 now says so out loud:
`window/showMessage` `Config contains unrecognized setting "diagnosticMode".`, with the same file otherwise
honoured (a control setting `reportUnusedCallResult: "error"` turned the same 26 diagnostics from severity 2 to
severity 1, proving the file was read). Nine channels were measured on the repository copy (336 source files,
the tree's 335 plus the session's never-opened probe):

| Channel | Files diagnosed | Never-opened file diagnosed |
|---|---|---|
| nothing, config file (`pyrightconfig.json`), `initializationOptions` in four shapes | 0 | no |
| `workspace/didChangeConfiguration`, `python.analysis.diagnosticMode` | **336** | **yes, 4 diagnostics** |
| `workspace/didChangeConfiguration`, `basedpyright.analysis.diagnosticMode` | **336** | **yes, 4 diagnostics** |

Serena cannot send `didChangeConfiguration` for this server, and `initializationOptions` (which Serena can
reach through the LS-specific setting named `initializationOptions`) is ignored by the server even when the key
provably arrives; the one key the server reads out of that channel is `disablePullDiagnostics`, whose consumer
is already false for this client, so its effect is unobservable. Workspace mode does work: 336 files pushed
within 4.5 s, the never-opened probe file diagnosed, the pull route agreeing, and it keeps working after an
edit. Its price is memory: **805.2 to 831.1 MiB tree (731.1 to 756.7 MiB node) against 219.5 MiB idle**, about
3.7 times the idle footprint, and neither `indexing: false` (827.8 MiB) nor `useLibraryCodeForTypes: false`
(831.1 MiB) reduced it. `workspace/diagnostic` (the LSP 3.17 workspace pull) is not answered: the request timed
out after 300 s.

**Costs**: node memory +11% in every variant (fixture 158.2 to 175.2 MiB, repository 382.6 to 423.6 MiB; the
tree reads 228.8 and 477.2 MiB), and every latency median up by 0.1 to 0.3 ms, which the fragment itself calls
sub-millisecond and not a property of the server. The repository latencies on the port's `record_observation`
are 0.2 / 2.9 / 2.5 ms (definition, references, rename) against the baseline's 0.2 / 4.2 / 3.2.

### 4.5 Corrections this section makes to the rest of the report

1. **pyrefly's C13 and C14 answers are `null`, not `[]`.** Section 3.2's cells, the C13/C14 evidence line and
   the reading in 10 say "empty list"; the transcripts hold `null` in both 1.2.0 and 1.4.0 (the baseline
   fragment's `[]` was its own transcription). An empty answer either way; the correction is that a client
   distinguishing `null` from `[]` sees `null`.
2. **C9 is invalid as written**, which section 8.1 already says; both re-measurement fragments skipped it, and
   pyrefly's and basedpyright's tables mark it "not run" rather than scoring it. Nothing else in 4 changes 8.1.
3. **C5, C6 and C7 are scored against the word-boundary sets, once and for all.** C5: 4 sites (`widget.py:10`
   the parameter, `widget.py:11` its read, `service.py:26` and `broken.py:6` the two keyword call sites). C6: 19
   occurrences, 18 code sites plus the `__all__` string, distributed `service 2, __init__ 2, broken 3, widget 2,
   ports 2, test_impl 5, impl 3`. C7: 10 occurrences, 9 that must change, the tenth being
   `STRING_PORT = "Port"`. Section 3.1's `*` columns say this; section 8.2 says why.
4. **C20's expectation for `impl.py`'s last line stands corrected** (section 8.3): that line is inside
   `cached_load`, and both re-measurement fragments that touch it answer `cached_load`.
5. **A baseline prose slip, not a version difference**: the original basedpyright fragment described
   `renameProvider` as `{'prepareProvider': True}`; both versions' own JSON also carries
   `workDoneProgress: True`. No behaviour is attached to this.
6. **The pyrefly configuration cost in section 6 moves**: the eight `search-path` entries were a bench
   artefact, and the operator's alternative is the one-line interpreter path at +58 MiB (4.3).
7. **Axis I's ty results now have a same-version basis as axis II**: section 5.8 is rewritten accordingly.

## 5. The claims the bench settles

**5.1 pyright's override edge is absent in both directions.** Renaming `Handler.handle` returns
`base.py:2` and `service.py:22` and neither `Upper.handle` nor `Lower.handle`; asking from the override side
(`rename_from_override`) returns the override alone, so there is no edge to traverse either way. The same
absence explains C1, C2 and C3, and it is the reference finder, not the rename path: `refs_Sink_emit` is
`[ports.py:18]` with `includeDeclaration=true` and `[]` with `false`. It is not a version artefact and not a
configuration artefact: reproduced on a fresh minimal project with no config, on both 1.1.403 and 1.1.414.
What pyright does do is resolve a call on a concrete receiver (`definition_of_upper_call` lands on
`Upper.handle`), which is why the gap is invisible until a rename is attempted. On this repository the same
shape costs a rename of `CatalogRepository.record_observation` its adapter: 2 sites, the declaration and one
call, while the structural implementation at `adapters/persistence_sqlite/catalog_repository.py:106` stays.

**5.2 basedpyright finds structural `Protocol` implementations but does not rename through them.** C13 returns
`StructuralPort` and `NominalPort` (plus the declaration) and C14 returns `InheritedDrawable`; on this
repository `textDocument/implementation` on `CatalogRepository` lists `SqliteCatalogRepository` and the test
double `_StubRepository`. Yet its rename set is exactly its references set, so C1 returns 2 of 6 and, on the
repository, renaming the port's `record_observation` returns **2 sites** while the two classes the
implementation request had just listed keep the old name. The consequence is stated plainly in the fragment:
the tree is left in a state `mypy --strict` rejects (the adapter no longer satisfies the protocol) and nothing
in the rename answer warns about it. Renaming from the adapter side instead reaches 71 sites across 9 files,
which is the opposite failure: the port's declaration and everything that goes through the protocol name stay
behind. The mechanism is narrowing: `port: CatalogRepository = repository  # mypy proves structural
satisfaction` hovers as `(variable) port: SqliteCatalogRepository`, so `port.record_observation(...)` binds to
the adapter symbol. The earlier bench (its summary is in `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`)
claims only the finding: "basedpyright alone finds a `Protocol`'s structural implementations". That finding
holds here, on the fixture and on the repository; reading it as rename coverage, which the fragment's own
"renaming reaches what the server understands" test invites, does not, and C1 is the falsifier.

**5.3 pyrefly renames a nominal hierarchy completely, and only pyrefly does.** C2, C3 and C4 come back 3 of 3,
3 of 3 and 4 of 4, with the raw edits quoted (`base.py:1:8`, `base.py:6:8`, `base.py:11:8`, `service.py:21:12`),
stable across a fresh session, matching the earlier bench's claim ("only pyrefly renames a nominal hierarchy
completely"), which this bench confirms and extends with the per-case reach. It is not a
general reach advantage: C1 is 5 of 6 and misses the structural implementation `StructuralPort.render` while
keeping `NominalPort.render`; C5 misses the cross-file keyword argument (1.4.0 fixes exactly that one, 4.3);
C12 misses both body uses of the fixture parameter. Its rename is exactly its reference index everywhere else,
the same equality the other servers show.

**5.4 ty answers `-32602` for any document not opened in the session, and files import lines as
declarations.** Every one of the 17 `textDocument/*` methods tried refuses a file that was never `didOpen`-ed:
`{"code": -32602, "message": "Document file:///.../lspfix/broken.py is not open in the session"}`, and its
advertised `diagnosticProvider` (including `workspaceDiagnostics: true`) never answers. **Correction: this is
a 0.0.25 statement.** At 0.0.89, 17 of the 18 methods probed answer on unopened documents, the fix being
0.0.84's "Support LSP requests against closed documents"; the pull diagnostic keeps answering but becomes a
silent empty report for a file that has errors, which is worse than the refusal (4.2, 5.8). The rest of this
claim stands at 0.0.89. This is harmless under
Serena because `solidlsp` opens every document before asking anything about it (`SymbolLocationRequest.execute`
wraps definition, references, implementation and rename in `open_file`, and the document-symbol path reaches
`ensure_open_in_ls()`), which is why the earlier bench saw working answers. The second half is subtler:
ty treats an `import` binding as part of the declaration, so `references` on `Widget` returns 18 sites with
`includeDeclaration: true`, including the six import lines, and 11 with `false`, dropping exactly those six plus
the definition. `includeDeclaration` is `false` in every reference request `solidlsp` makes, which is why ty
appeared to omit import lines: references of the `CatalogRepository` protocol returned 6 sites where its own
rename produced 13 edits, the missing 7 being the six `from ... import CatalogRepository` lines and the
definition.

**5.5 jedi's rename is its references plus a `difflib` diff.** `jedi.Script.rename` is `get_references(...)`
followed by a refactor, so every rename answer is a references answer: C1 returns 4 reference locations and a
rename that changes exactly those 4 lines. `includeDeclaration` is ignored (byte-identical lists for `true` and
`false`, and C22 sent `false` and still got the definition back). `prepareRename` is not implemented
(`-32601`, no `prepareProvider` advertised). The edits are char-level `difflib` opcodes, which is why the
fragment applied every one of them and diffed: every applied set produced the intended text, cosmetic but not
corrupting, and the incompleteness is inherited from references (C1, C2, C4 and C12 applied verbatim leave a
protocol implementation behind, an abstract class uninstantiable, a detached override, and a pytest fixture
referenced by nobody).

**5.6 Diagnostics: three different scopes, and pyrefly's silent `basic` preset.** pyright and basedpyright
index the whole tree (335 source files in 0.26 s) and diagnose only opened files: opening one file produced
exactly one `publishDiagnostics`, and a never-opened broken file answers the pull with `{"items": []}`.
basedpyright can be switched to workspace-wide checking over `workspace/didChangeConfiguration`
(`{"settings": {"python": {"analysis": {"diagnosticMode": "workspace"}}}}` pushes 336 files) but the same
setting in a `pyrightconfig.json` did not take effect, with a control proving the file was read.
ty refuses unopened documents outright and pushes only for files open in the session (6 of 333 after 25 s;
at 0.0.89 the refusal is gone and a pull on an unopened file answers an empty report, 4.2).
pyrefly is the only one that diagnoses the whole tree, because Serena's `workspace/configuration` reply sets
`diagnosticMode: workspace`; in the bare stage it published for 228 files, 1,046 of them `missing-import`.
jedi has no type checking at all: its diagnostic channel is a debounced syntax-error report, so `broken.py`
yields an empty array while a syntax error is reported. And pyrefly's fixture answer is a **configuration
artefact, not a capability**: with no `[tool.pyrefly]` section at all it runs the `basic` preset and reports
nothing, an empty `[tool.pyrefly]` reports both constructed errors, `preset = "basic"` suppresses them,
`preset = "default"` restores them, a `[tool.mypy]` section alone flips it, and the CLI cross-check agrees
(`--preset basic` prints `INFO 0 errors`). The pull route makes it worse: pyrefly does not advertise
`diagnosticProvider`, yet answers `textDocument/diagnostic` with `{"items": [], "kind": "full"}`, which reads
as "no problems" when it means "not configured".

**5.7 The `__all__` string splits the field, and the dataclasses blind spot does not.** pyright and
basedpyright rewrite the `"Widget"` and `"Port"` entries inside `__all__` (`lspfix/__init__.py:4:21->Card`);
ty, pyrefly and jedi leave the string, and pyrefly's fragment argues leaving it is correct while jedi's notes
the rename then leaves `__all__` pointing at a name that no longer exists. The protocol counts the string as a
site. Conversely, all five miss the same `small.title` site and the same `replace(size=4)` keyword, so the
`dataclasses.replace` blind spot discriminates nothing between them.

**5.8 The version gap between the two axes is now measured.** Axis I ran Serena's pin, **0.0.25**; axis II
ran `uvx ty@latest`, **0.0.89**. Section 4.2 re-measures the language-server cases on 0.0.89, and the LSP
answers move in exactly two places: C13 and C14 are answered partially instead of erroring, and a pull on an
unopened document becomes a silent empty report instead of a refusal. All twelve renames are byte-identical,
the import-line classification is unchanged, `workspace/diagnostic` still never answers and `typeHierarchy/*`
is still half-implemented, so the `-32602` precondition this claim used to state is historical: it describes
0.0.25 only. Axis II was measured on 0.0.89 from the start (section 7).

## 6. What each server needs from this repository

The repository already carries the pyright configuration in its root `pyproject.toml`, and the reader is the
language server, not the gate:

```toml
# For editors' and Serena's language server, not the gate: without the venv, no import resolves.
[tool.pyright]
venvPath = "."
venv = ".venv"
```

**pyright.** Nothing invented, and no second environment: the copy pointed at the original `.venv` read-only,
materialised as a real `.venv` directory holding symlinks to `bin/python`, `bin/python3`, `pyvenv.cfg` and
every `site-packages` entry, **with the eight `_editable_impl_*.pth` files rewritten** to name the copy's
`packages/*/src`. No `extraPaths`, no `pythonPath`, no `pyrightconfig.json`, no `didChangeConfiguration`. A
clone carries no `.venv`, so a fresh checkout needs one (the committed block points at it); hiding it costs 13
`reportMissingImports` on `webui/composition/app.py` plus 1 on `catalog_repository.py`, while workspace-internal
resolution survives.

**basedpyright.** `uv sync --dev` in the clone (1.0 s, 271 MiB), nothing else: the committed block as is. With
the block deleted, basedpyright still resolved `./.venv` on its own and every answer was identical, so for
basedpyright the committed block is redundant and for pyright it is needed. A clone would have to carry a
synced venv either way.

**ty.** A `ty.toml` at the copy root, the only file added, verbatim:

```toml
[environment]
python = "/home/geoffrey/Repositories/emule-indexer/.venv"
extra-paths = [
  "packages/crawler/src",
  "packages/crawler_testing/src",
  "packages/amule/src",
  "packages/matching/src",
  "packages/vex_checks/src",
  "packages/template_checks/src",
  "packages/coverage_checks/src",
  "packages/amule_bump/src",
]
```

`python` gives the third-party site-packages; `extra-paths` outranks the venv's editable paths ("first
priority in module resolution"), so the members resolve inside the copy. Whole-tree proof by CLI on the same
tree: `Found 68 diagnostics` and 0 `unresolved-import`, against `Found 736 diagnostics` of which 690
`error[unresolved-import]` with no configuration. On the real tree ty documents that it finds `./.venv` itself,
so `ty.toml` should not be needed there; that is the fragment's documented inference, not a measurement it took.

**pyrefly.** Two blocks plus a preset, verbatim:

```toml
[tool.pyrefly]
search-path = ["packages/amule/src", "packages/amule_bump/src", "packages/coverage_checks/src", "packages/crawler/src", "packages/crawler_testing/src", "packages/matching/src", "packages/template_checks/src", "packages/vex_checks/src"]
python-interpreter-path = "/home/geoffrey/Repositories/emule-indexer/.venv/bin/python"
preset = "default"
```

`search-path` alone resolves the eight members; adding the venv drops `missing-import` from 147 to 8, and the
8 are test-support packages not installed in the venv (`tests.fakes`, `tests.integration.conftest`, two test
modules). `preset = "default"` is a no-op once a configuration file exists; it is the **absence** of any
configuration that selects `basic` (5.6). **Correction (4.3):** the eight `search-path` entries were a bench
artefact of pointing a copy at the original repository's venv. On the real tree, where the venv and the
workspace are the same tree, the single line
`python-interpreter-path = "/home/geoffrey/Repositories/emule-indexer/.venv/bin/python"` resolves all eight
members and every third-party import, at about +58 MiB resident against the `search-path` variant.

**jedi.** `initializationOptions`, on top of the base options
`{"workspace": {"symbols": {"ignoreFolders": [".nox", ".tox", ".venv", "__pycache__", "venv"], "maxSymbols": 0}}}`:

```json
{"workspace": {"environmentPath": "/home/geoffrey/Repositories/emule-indexer/.venv",
               "extraPaths": ["/tmp/lsp-bench/jedi/repo/packages/crawler/src", "... the copy's eight members ..."]}}
```

On the copy, `extraPaths` for the eight members is what keeps answers inside the copy; on the real repository,
verified read-only, `environmentPath = .venv` alone resolves correctly (references 13 sites in 7 files,
`definition` of the annotation lands in the repository's own file, `MatchingEngine` resolves), so a clone is
what needs the extra configuration, not the tree.

**The trap all five fragments hit, in the same shape.** Pointing a copy at the real `.venv` makes uv's
editable installs bind the members to the original checkout, because `_editable_impl_*.pth` holds absolute
paths into `/home/geoffrey/Repositories/emule-indexer/packages/*/src`. pyright: every `import p2pwatch...`
resolved outside the workspace and renaming `CatalogRepository` inside the copy returned 1 site instead of 13.
basedpyright: definition landed at `../../../../home/geoffrey/Repositories/emule-indexer/...`, references and
rename collapsed to 1 site, the implementation request returned only the declaration, and the opened real file
showed 0 diagnostics. ty: definition landed in the original tree, references returned `null`, rename produced 1
edit. pyrefly: no result in any stage landed outside the copy only because `search-path` outranks
`site-packages-path`; the fragment records the `.pth` hazard explicitly. jedi: 1-site collapse on the copy, and
its read-only run on the real tree is what shows the same configuration is correct where the venv's paths and
the workspace are the same tree. Two escapes were measured and work: give the copy its own venv (`uv sync`), or
outrank the venv roots with `extraPaths`/`extra-paths`/`search-path`.

## 7. Axis II in full: ty against mypy `--strict` in the gate

Provenance: repository `fd9d681`, work copy `/tmp/lsp-bench/checker/repo` with `uv sync --dev` (1.9 s), mypy
2.3.1 in `<copy>/.venv`, ty **0.0.89**. The gate's `type-check` task runs eight sequential commands,
`mypy src tests` per package (`mypy src` for `crawler_testing`), because each package's `tests` is itself a
package.

**Version note.** This section's ty is **0.0.89** (`uvx ty@latest`), while axis I's language-server cases were
measured on Serena's pin, **0.0.25**. The two axes therefore did not measure the same artefact when this
section was written; section 4.2 re-measures the language-server side on 0.0.89 and section 5.8 records where
the two now stand.

### mypy as the gate runs it: zero diagnostics, 333 files

| Package | Files | Cold median (3 reps, cache cleared) |
|---|---|---|
| matching | 26 | 1.312 s |
| crawler | 222 | 3.226 s |
| crawler_testing | 12 | 1.714 s |
| amule | 16 | 1.230 s |
| vex_checks | 30 | 1.179 s |
| template_checks | 6 | 1.304 s |
| coverage_checks | 8 | 1.353 s |
| amule_bump | 13 | 1.190 s |
| **sequence, gate order** | 333 | **12.51 s** (sum of cold medians); 12.62 s median of 5 whole-sequence runs; 0.705 s warm |

All eight report `Success: no issues found`, re-checked with `--no-incremental`; peak RSS of the largest run
(crawler, cold) 272.6 MiB. That mypy really checks this tree was proven with a deliberate probe
(`def _gate_probe(a: int) -> str: return a` in `domain/file_key.py`) which mypy reported, then removed.

### ty: the same tree, its own scope

ty 0.0.89 has no `--strict`; strictness is a rule table (140 rules: 97 default `error`, 25 `warn`, 18
`ignore`). Import resolution needs no configuration at all from the repository root: ty finds the root `.venv`,
resolves all eight members and every third-party dependency, and reports no `unresolved-import`.

| ty configuration | Diagnostics | Errors | Warnings |
|---|---|---|---|
| default rule levels | 39 | 38 | 1 (Corrected 2026-10-17, section 11: was 39 errors and 0 warnings) |
| the docs' recommended strict block | 55 | 54 | 1 |
| strict block plus `--error all` | 116 | 115 | 1 |

The strict block that was written (the only one of its four lines that fires on this tree is
`unsound-return-statement`):

```toml
[tool.ty.rules]
dynamic-function-decorator-return = "error"
missing-type-argument = "error"
possibly-unresolved-reference = "warn"
unsound-return-statement = "error"
```

Two scope facts the gate would have to decide rather than inherit. ty's default scope is the whole project
root, a superset of the gate's file set: with no `[tool.ty.src]` at all, a planted error in `scripts/` is
reported and three deliberate `unresolved-reference` errors fire in `vulture_whitelist.py`, so
`[tool.ty.src] include` (the 15 paths of the eight packages' src and tests) is what makes the two scopes
comparable. And the per-package shape the gate uses breaks resolution: `cd packages/crawler && ty check src
tests` gives `Found 174 diagnostics`, all `unresolved-import` (`httpx`, `catalog_matching.ed2k_link`, ...),
because ty looks for a venv at the project root it discovers there; `--python ../../.venv` brings it back to
the same answer as the root run. Verified: the single root invocation and the eight per-package runs produce
identical sorted diagnostic lines, and the single one is about three times cheaper.

### The delta

**mypy-only diagnostics: none.** mypy reports zero, so there is no list to transcribe; that is a fact about the
tree, not about the tools. The substantive comparison is the `--strict` capability table below.

**ty-only diagnostics: 55, in two classes.** Class 1, 39 diagnostics: every one sits on one of the 36 lines
carrying a mypy-coded `# type: ignore[...]`, and they are not new findings. Proven by deleting three ignores and
re-running mypy, which then reports the same three errors at the same three positions
(`apprise_notifier.py:66`, `test_clock.py:49`, `test_file_key.py:19`). Class 2, 16 diagnostics mypy `--strict`
genuinely does not report: 14 `unsound-return-statement`, 1 `deprecated`, 1 `invalid-argument-type`. Two of
those 16 are **false positives**, both minimized:

1. `packages/amule_bump/src/amule_bump/body.py:47`, `unsound-return-statement`. Five-line repro:
   `kept, inside = [], False`, `kept.append(line)` in a loop, `return "".join(kept).strip()`. ty infers
   `kept: list[Unknown]` and `"".join(list[Unknown])` as `Unknown`; mypy infers `list[str]` and `str`, and the
   code is right. Also reproduces with a nested `if`, not with a plain `kept = []`.
2. `packages/coverage_checks/src/coverage_checks/own_tests.py:80`, `invalid-argument-type`.
   `max(chosen, key=lambda path: len(path.name), default=None)` over a `list[Path]`; ty types the `key`
   parameter as `Path | None`. mypy is right.

The other 14 are true by the rule and benign, with the cause named in each (typeshed's `re.Pattern.split`
returning `list[Any]`, `float.__pow__` returning `Any`, `sqlite3` `fetchall()`, `argparse.Namespace`
attributes, `json.loads(...)["query"]`). The rule is a soundness check mypy does not have: `--warn-return-any`
fires only on a bare `Any`, so `list[Any]` flowing into `list[Row]` is silent under `--strict` while
`unsound-return-statement` catches it. It is both a gain and a false-positive source.

### The 36 `# type: ignore[...]` and how each tool reads them

Census (`rg -n --no-heading '# type: ignore' packages`): **36 comments, 38 codes, none bare** (15 `misc`, 10
`attr-defined`, 4 `arg-type`, 4 `operator`, 2 `no-any-return`, 1 each `assignment`, `method-assign`,
`call-overload`). Established with a 13-line probe that puts each spelling on a failing and a passing line:

| Spelling | ty 0.0.89 | mypy 2.3.1 `--strict` |
|---|---|---|
| `# type: ignore` (bare), on a failing line | suppresses | suppresses |
| `# type: ignore` (bare), on a passing line | `warning[unused-type-ignore-comment]` | `error: Unused "type: ignore" comment [unused-ignore]` |
| `# type: ignore[ty:invalid-argument-type]` | suppresses | does not suppress, reports `unused-ignore` |
| `# ty: ignore[invalid-argument-type]` | suppresses | not a mypy directive |
| `# type: ignore[arg-type]`, a mypy code | **does not suppress, and is not reported as unused** | suppresses |
| `# type: ignore[misc]`, a mypy code | **does not suppress, and is not reported as unused** | suppresses |

So ty reads the comment only for a bare `ignore` or a `ty:`-prefixed code. The 36 coded comments of this tree
are inert text to ty: they suppress nothing and are not flagged as stale either. That single fact accounts for
39 of the 55 diagnostics. `unused-ignore-comment` is the counterpart of `warn_unused_ignores`, and its coverage
is not equivalent: an unused **mypy-coded** ignore is caught by mypy and invisible to ty. A warning in ty is
not free either: `ty check` exits 1 on a warning-only file under default settings, so `warn`-level rules do
gate, and `--exit-zero-on-warning` must not be used if `redundant-cast` and `unused-type-ignore-comment` are to
keep gating.

**Re-measured across versions: identical on 0.0.25, 0.0.87 and 0.0.89.** The re-measurement checked the eight
probe files one at a time with each of the three versions (`ty check --no-progress --output-format concise`,
binaries taken from `~/.cache/uv/archive-v0/`), reporting the same verdict on all three; re-run independently
while merging this section, as a directory, with the same seven lines and the same total:

```
$ cd /tmp/lsp-bench/checker/ignore4 && uvx -p 3.13 --from ty==<0.0.25|0.0.87|0.0.89> ty check --no-progress --output-format concise .
2_mypy_code.py:5:11: error[invalid-argument-type] Argument to function `takes_int` is incorrect: Expected `int`, found `Literal["b"]`
3_ty_prefix_wrong_rule.py:5:11: error[invalid-argument-type] ... found `Literal["c"]`
3_ty_prefix_wrong_rule.py:5:32: warning[ignore-comment-unknown-rule] Unknown rule `arg-type`
6_ty_code_wrong_rule.py:5:11: error[invalid-argument-type] ... found `Literal["f"]`
6_ty_code_wrong_rule.py:5:17: warning[unused-type-ignore-comment] Unused `type: ignore` directive
7_combined_wrong_ty.py:5:11: error[invalid-argument-type] ... found `Literal["g"]`
7_combined_wrong_ty.py:5:42: warning[unused-type-ignore-comment] Unused `type: ignore` directive: 'redundant-cast'
Found 7 diagnostics
```

The same seven lines and the same `Found 7 diagnostics` on each of the three versions. What the probes single
out, file by file: the bare `# type: ignore` (1), the `ty:` directive (4), `arg-type` combined with the right
`ty:` code (8) all suppress; `type: ignore[arg-type]` alone (2) neither suppresses nor is flagged, because a
bracket is registered only when it carries at least one `ty:`-prefixed code, and it then filters on the
ty-named rules only; the wrong-rule ty brackets (3, 6, 7) are registered, so they are flagged, 3 as
`ignore-comment-unknown-rule` and 6 and 7 as `unused-type-ignore-comment`, and suppress nothing. The 36
mypy-coded comments of this repository carry no `ty:` code, so they are inert text to ty on every version
tested and the 39 diagnostics stand; the repository half is its own check, `rg -n --no-heading
'type:\s*ignore\[[^]]*ty:' packages` over `/tmp/lsp-bench/checker/repo`, which exits 1 with no match. The
mechanism is stated in ty's own docs, saved at `/tmp/lsp-bench/checker/ty-suppression.md`: "Codes without a
`ty:` prefix are ignored, which makes it possible to combine suppressions for multiple type checkers in a
single comment."

### The four `--strict` capabilities with no ty rule

Each was probed with a minimal file mypy `--strict` rejects, then re-checked with `ty check --error all`, the
most aggressive setting ty offers; files under `/tmp/lsp-bench/checker/strictprobe/`.

| # | mypy flag | mypy code | ty default | ty `--error all` | Repro |
|---|---|---|---|---|---|
| 1 | `--disallow-subclassing-any` | `misc` | silent | **missed**, no counterpart rule exists | `subclass_any.py`: `Base: Any = object` then `class Derived(Base)` |
| 2 | `--disallow-untyped-defs` (with `--disallow-untyped-calls`, `--disallow-incomplete-defs`) | `no-untyped-def`, `no-untyped-call` | silent | **missed**, docs say "None yet" (ty issue #4381), routed to ruff `ANN` | `untyped_call.py`: an unannotated function called from typed code, which mypy rejects twice and ty not at all, so the function's body may hold anything; `untyped_decorator.py` loses the `no-untyped-def` half |
| 3 | `--no-implicit-reexport` | `attr-defined` | silent | **missed**, docs say "None yet for non-re-exported names in runtime files" (ty issue #200) | `reexport_consumer.py`: `from pkg import name` where `pkg/__init__.py` re-exports `name` implicitly |
| 4 | `--strict-equality` | `comparison-overlap` | silent | **missed** on the probe's value form; `redundant-condition-strict` (default `ignore`, since 0.0.79) catches the same comparison inside an `if` only (Corrected 2026-10-17, section 11: was "no rule matches"); `strict-equality-semantics = true` adds nothing | `strict_equality.py`: `number == text` with `number: int`, `text: str` |

A fifth escape shape follows from the ignores rather than from a flag: a stale mypy-coded ignore is
undetectable under ty (`unused_ignore.py`). Of the 13 flags `--strict` turns on, the other nine have a ty
counterpart, three of them configuration gaps rather than capability gaps (`--disallow-any-generics`,
`--warn-redundant-casts`, `--warn-return-any` all exist behind a level change, the last being stricter than
mypy), and `--disallow-untyped-decorators` is partly covered by `dynamic-function-decorator-return`. The
four rows above are the ones that matter here: they are exactly the shapes `--strict` was adopted to forbid,
and nothing in the tree would catch a regression into them.

**How each row was established, where it matters**: all thirteen flags were probed with a minimal file, and
the 140-entry rule table with its default levels comes from `ty explain rule` (a run). Two things are weaker
and are marked as such: the `--disallow-subclassing-any` and `--strict-equality` rows say "no counterpart
exists" on the strength of a name search over that measured table plus their probes, not of a behavioural
proof beyond them; and the claim that ty's `unused-ignore-comment` is the counterpart of mypy's
`warn_unused_ignores` is read from ty's migration page, while what was measured here is only the behaviour of
the spellings on this tree.

### Cost

| Measure | mypy | ty |
|---|---|---|
| Eight sequential per-package runs | 12.51 s (sum of cold medians), 12.62 s (5-rep median) | 0.384 s (sum of per-package medians, each with `--python ../../.venv`) |
| Whole set in one invocation | not the gate's shape | 0.126 s (5-rep median, direct binary), 0.141 s through `uvx` |
| Warm cache | 0.705 s | no cache written; 0.126 s either way |
| Peak RSS | 272.6 MiB (crawler) | 174.1 MiB (whole repository, one run; 156.0 MiB crawler alone) |

## 8. Where the protocol itself was wrong

Two of these matter more than any single cell in section 3.

### 8.1 C9 asks for a rename of a member that does not exist

`service.py:24` reads `small = widget.replace(size=4)`, and `Widget` is a `@dataclass(frozen=True)`.
`dataclasses` synthesizes `__init__`, `__eq__`, `__repr__` and `__hash__`, and in 3.13 the `__replace__` dunder
of the copy protocol; it never generates a `replace` method. `replace` is the module-level
`dataclasses.replace(obj, **changes)`. The fixture's call is therefore an attribute error at runtime, and
`rg -nw replace` over the fixture finds exactly one occurrence: that line. ty's own pushed diagnostic says so
in as many words: `unresolved-attribute: Object of type Widget has no attribute replace` at `service.py:24`,
and its hover of `small` returns `Unknown`. **Every one of the five servers was right to leave the keyword
alone**, so C9 measures nothing about keyword-argument renames; the five "2 of 3" cells in 3.1 are five servers
correctly declining an invalid site. Two fragments read the miss as a real blind spot (pyright: "the
dataclass-generated `replace` keyword is not linked to the field"; basedpyright confirms the earlier bench's
"no server renames a `replace()` keyword"), one states the cause (pyrefly: "a `dataclasses.replace`-generated
method pyrefly does not model"), and ty's fragment establishes it with the diagnostic above. The earlier
bench's entry on this point is therefore void rather than confirmed: nobody can rename a member that the class
does not have. The real shapes of that question are
`dataclasses.replace(widget, size=4)`, whose keyword is bound to the field by the signature of a real
function, and a `NamedTuple`'s `_replace`. Neither was measured, so the question is **unmeasured**, not
answered. Its valid cousin, C5, does discriminate: a plain function's keyword argument called from another
module is renamed by pyright, basedpyright and ty, and missed by pyrefly (with a same-file control proving it
is the cross-file case specifically) and by jedi.

### 8.2 The expected counts of C5, C6 and C7 are lower than the word-boundary sets

The protocol's own method section demands the occurrence set be derived with `rg -w` before running a rename;
for these three cases the case table contradicts that. Re-verified for this merge: `limit` has 4 occurrences in
`.py` (the protocol says 2), `Widget` has 19 (18 code sites plus the `__all__` string, the protocol says 13),
`Port` has 10 of which 9 must change (8 code sites plus the `__all__` string; `STRING_PORT = "Port"` must not,
the protocol says 7). The correct report is per server, not a ratio against the wrong number: pyright 4/19/9,
basedpyright 4/19/9, ty 4/18/8 (missing only the `__all__` string), pyrefly 2/18/8 (missing the cross-file
keyword argument and the `__all__` string, on two different criteria), jedi 2-or-3/18/8. Every fragment caught
the discrepancy independently and said so (pyright: "the protocol's 2 undercounts by construction";
basedpyright: "the two extra sites are real uses of the parameter that the expected list omitted, and their
absence would have been the bug"). No server is penalised for the protocol's arithmetic in this note.

### 8.3 C20's expected answer for the last line of `impl.py` is wrong

`impl.py`'s last line (line 48, `    return name`) is inside `cached_load`, whose range is `46:0-48:15`. The
correct innermost symbol is `cached_load`, not "none or the module"; the protocol's parenthetical assumed a
blank line that is not there. Four fragments answered `cached_load` and treated it as finer than allowed;
ty's fragment states the correction outright ("so `cached_load` is the correct innermost symbol"), and it also
measured what the protocol probably meant: one line past EOF answers `<module>`. jedi's null for the same
position is a client artefact, not a server answer (see section 9).

## 9. What could not be measured

Gathered from the six fragments, each with its reason.

**Common to the five.** Serena's own tool layer was never driven: all requests went through `solidlsp` or a raw
client, so `find_symbol`, `find_referencing_symbols`, `rename_symbol` and their kind filters, the
`UnifiedSymbolInformation` reshaping and `apply_workspace_edit` are unmeasured. The C18 kind deviations and
pyrefly's C19 duplicates are what the **servers** return, not what a Serena tool hands back. C12's real answer
(the pytest fixture-to-parameter link) is out of reach of every LSP: it is a runtime name convention, so all
five would score equally and pyright's fragment calls its 1 of 5 "the ceiling of the static answer, not a
defect of one server". Nothing under `/home/geoffrey/Repositories/emule-indexer` was written, and no server
was rooted there except jedi's read-only probe. Cold-cache startup is unmeasured in every fragment (`uvx` and
page caches were warm). Memory figures are not comparable across fragments: some sum the process tree, some
report the server alone, `uvx` stays alive as a parent (37 to 45 MiB, never `exec`-replaced), and ty's fragment
notes that RSS double counts pages shared between `uvx` and its child, so its tree totals overstate the real
footprint. Timing differences below a millisecond should not be read as server properties.

**pyright.** Whether a `WorkspaceEdit` applies cleanly (edits were retrieved, never applied; the shape,
`documentChanges` and never `changes`, was measured). `npx` versus `uvx` only on the one minimal override case
(identical). Pull diagnostics beyond the two protocol states. Everything else it advertises (declaration,
type-definition, document highlight, call hierarchy, completion, signature help, code actions, an empty
`executeCommand` list) and multi-root workspaces. Semantic tokens and inlay hints are not offered at all.

**basedpyright.** Why `diagnosticMode: "workspace"` in a config file did not take effect while the same
setting over `didChangeConfiguration` did (the file was proven read). Baseline mode, inlay hints, type
evaluation, Jupyter, code actions and completion. Multi-root. C22 without the file-change notification
(whether the mtime alone would have been noticed).

**ty.** `workspace/diagnostic` is advertised (`workspaceDiagnostics: true`) and never answers: with
`previousResultIds` there was no response in 90 s and no `$/progress` frame, `{}` is rejected with `-32602`.
Sub-range incremental edits (`didChange` always replaced the whole document). `notebookDocumentSync`,
`completionProvider`, `inlayHintProvider` and `codeActionProvider` were only sanity-checked. Whether a Serena
tool degrades or surfaces the `-32601` on `textDocument/implementation`: `supports_implementation_request()` is
read nowhere in `serena/`. The repository numbers were taken on a clone pointing at the operator's `.venv`; the
claim that the real tree needs no configuration is the fragment's documented inference, not a measurement.

**pyrefly.** Cold-process startup. The retry on `RequestCancelled`/`ContentModified` (never triggered). The
`-32600 Third-party symbols cannot be renamed` refusal, hit once when a position landed in a docstring under
the bare configuration and then avoided by pinning positions to code lines. The per-stage diagnostic counts are
timing-sensitive (233/118/17/17 at the 6 s mark against 240/121/20/20 by session end; the codes and per-file
content were stable). The `pyrefly.toml` fallback was never triggered, both trees having a `pyproject.toml`.

**jedi.** The bare Serena command never ran: `jedi-language-server` is not on `PATH` and Serena provisions
nothing for `python_jedi`, so every figure is for the `uvx`-started process and includes its 40 to 45 MiB
launcher. Type diagnostics over the wider repository were not swept (the server has none to sweep with).
Whether `maxSymbols: 0` really lifts a default limit of 20 could not be discriminated (9 results for `main`
under both 0 and 20), and `ignoreFolders` had no ignored directory to test. Its C5 row does not state whether
`broken.py:6`'s keyword argument was renamed.

**Axis II.** Whether `[tool.ty.analysis] strict-equality-semantics = true` closes the `--strict-equality` gap
(the probe was not re-run with it). The `Concatenate` half of `--extra-checks`. Whether ty's two false
positives are fixed in a newer version (0.0.89 only). Whether the timings hold under a different rule set.
`warn_unused_configs` was not chased.

**The re-measurements' own limits (section 4).** pyright and jedi were not re-measured at their latest
releases, so nothing can be said about what 1.1.414 or a newer jedi changes beyond the one pyright A/B. ty
0.0.89's `workspace/diagnostic` silence is "no answer in 300 s on a ten-file fixture", not "never", though no
`$/progress` frame arrived while the server kept pushing diagnostics; the 33 to 7 drop in
`invalid-argument-type` on the repository was not audited case by case (one vanished false positive was
verified); its 90 to 127 MiB repository RSS jump is larger than the version can explain and was not repeated;
and the `symlink` repository variant, the one the baseline called a trap, was not re-run on 0.0.89 although
0.0.84 and 0.0.85 both touch environment resolution. pyrefly's stage (e) two-root result is a bench artefact
by construction, its per-stage diagnostic counts are timing-sensitive, its `workspaceIndexingLimit` (2000
files) was never reached and so is untested, and `preset = "strict"` beyond the fixture and the
`[tool.basedpyright]` preset mapping were not enumerated. basedpyright's `client/registerCapability` during
start-up could not be captured (the server installs its own handler early), so the claim that no workspace
diagnostics capability is registered rests on observation after start plus the source; which upstream commit
changed class hover is located in the bundle but not tied to a pyright PR; and none of the three Serena
overrides was watched in a live Serena session, only built and read at the provider level.

## 10. Reading of the bench

Neutral, per criterion, and without a winner; the operator takes that decision on this report.

**Renaming a nominal hierarchy** (C2, C3, C4): pyrefly alone, and completely. Every other server returns the
declaration and its direct references, which for C4 means the renamed call still type-checks and silently
stops dispatching to the overrides.

**Renaming through a structural `Protocol`** (C1, and the repository's dominant shape): nobody. pyright,
basedpyright and ty return 2 of 6, pyrefly 5 of 6 (missing the structural implementor), jedi 4 of 6. On this
repository that means every one of the 21 ports can be renamed to a state `mypy --strict` rejects, silently.

**"Who implements this port"** (C13, C14): basedpyright alone, and on this repository it is the request that
names `SqliteCatalogRepository` and the test double. pyright and jedi refuse the method at every version; ty
answers it from 0.0.89 but only for nominal subclasses, never the structural implementor (on `CatalogRepository`
it returns the Protocol itself, 4.2); pyrefly advertises the capability, returns `null` at a class position and,
at a method position, only the nominal override (4.3). The trade-off is the shape of the whole bench: the server
that answers "who implements this" (basedpyright) does not follow the nominal edge on a rename, and the server
that follows the nominal edge (pyrefly) returns nothing for the repository's structural idiom; no server does
both, at the pinned or at the latest versions.

**Renaming a class, a module-level constant or a module-level function** (C6, C7, C10, C11): pyright and
basedpyright complete, including the `__all__` string; ty, pyrefly and jedi complete on every code site and
leave the string, which is the one place where "complete" is a judgment call the protocol already made (it
counts the string as a site, and leaving it breaks `from lspfix import *`).

**Keyword arguments** (C5): pyright, basedpyright and ty reach the cross-file keyword call site; pyrefly and
jedi do not, pyrefly joining the first group at 1.4.0 (4.3). This is the criterion the invalid C9 was supposed
to measure (8.1).

**The `dataclasses.replace` shape** (C8, C9): a five-way tie in the wrong direction; all five miss the same
site, so it discriminates nothing.

**Diagnostics**: basedpyright the richest (errors plus warnings with rule codes and doc links, workspace mode
available over `didChangeConfiguration`), pyright the most economical (both constructed errors, precise rules,
opened files only), ty correct on opened files and refusing everything else at 0.0.25 (a silent empty report
rather than a refusal at 0.0.89, 4.2), pyrefly whole-tree but
configuration-dependent (silently `basic` with no config file, and an empty pull report that reads as "no
problems"), jedi syntax-only. Whole-tree symbols with opened-files-only diagnostics is the majority behaviour
(pyright, basedpyright, ty); pyrefly is the only whole-tree diagnoser; jedi has no index and pays per query.

**Cost**: ty and pyrefly are the lightest and fastest by a wide margin (0.023 s and ~0.03 s to ready; 84 and
100 MiB on the fixture), pyright and basedpyright the heaviest (175 to 214 MiB on the fixture, 278 to 481 MiB on
the repository, both starting at 0.31 to 0.34 s), and jedi sits in between on memory with per-request costs one
to two orders of magnitude above the others (rename 10.6 ms on the fixture, 90.6 ms on the repository) because
it walks and parses on demand. pyright carries a one-off 2 s wait in Serena before the first definition or
references request, which no other server adds. At the latest releases (4.2, 4.4), ty stays in the same place
(14 ms to initialize, 80 MiB), basedpyright gains about 11% of node memory and 0.1 to 0.3 ms per median, and
pyrefly's one-line configuration costs +58 MiB against the eight-entry `search-path` variant (4.3).

**Axis II, in the same neutral tone**: ty is 100 times faster than the gate's mypy shape (0.126 s against
12.6 s cold) with lower peak memory, and it sees things `--strict` does not (`unsound-return-statement`),
including two false positives on this tree. Against that, four `--strict` capabilities have no ty rule at all,
the 36 mypy-coded ignores are inert to it (39 of its 55 diagnostics), and the two configurations the gate would
need (a scope include and a `--python` for the per-package shape) are new operator-facing decisions rather than
translations of the current gate.

## 11. Re-measurements for the spec review (2026-10-17)

The review of `agents/specs/2026-10-17-serena-and-the-language-servers.md` re-ran the claims that spec rests on
and measured the one it bets on, which no earlier section measured: the rename once a port is an ABC. One agent,
its own stdlib LSP client (initialize, `didOpen` of the target file only, as Serena does), servers through
`uvx` at pyrefly 1.4.0, pyright 1.1.414, basedpyright 1.40.2 and ty 0.0.89 (versions from `serverInfo`). The
fixture was rebuilt from section 2, byte-identical to revision `b050f86` (`diff -r`). The repository side ran
on a `git clone --no-hardlinks` at `bc459b8` (no code change since `fd9d681`) with its own `uv sync --dev` venv,
pyrefly configured with `[tool.pyrefly] python-interpreter-path = "./.venv/bin/python"` and nothing else.
Evidence under the review session's scratchpad (`remeasure/`, ephemeral like `/tmp/lsp-bench`): `lsp.py`,
`run_fixture.py`, `run_repo.py`, `run_ready.py`, `apply_rename.py`, raw answers in `out/`.

**Reproduced, unchanged**: C1 (pyrefly 5 of 6, the three others 2), C2, C3, C4 (pyrefly 3, 3, 4; on C3 the
others touch the declaration alone, the call going through `sink: NominalSink`), C12 (pyrefly 3 of 5, the
others 1).

**`record_observation` on the repository.** Ground truth: 75 code sites in 12 files (the port, the adapter
`SqliteCatalogRepository`, the test stub `_StubRepository` of `tests/ports/test_catalog_repository.py`, and 72
calls); a 76th mention is a docstring. Sites / files per rename:

| Rename from | pyright | basedpyright | ty | pyrefly |
|---|---|---|---|---|
| today, the `Protocol` port's method | 2 / 2 | 2 / 2 | 2 / 2 | 4 / 4 |
| today, the adapter's method | 71 / 9 | 71 / 9 | 71 / 9 | 70 / 9 |
| `CatalogRepository(ABC)`, adapter and stub inheriting it: the port's method | 2 / 2 | 2 / 2 | 2 / 2 | **75 / 12** |
| the same, from the adapter's method | 71 / 9 | 71 / 9 | 71 / 9 | 70 / 9 |

pyrefly's 75 edits, applied: `mypy` clean over the crawler's 222 files, the crawler's unit suite `1400 passed`.
The edge is **one-way**: from the adapter, pyrefly does not climb to the ABC, and the 70 edits applied leave
`Cannot instantiate abstract class "SqliteCatalogRepository" with abstract attribute "record_observation"` in
8 files. After the conversion basedpyright and ty list both implementers for `implementation` at the method,
yet still rename 2 sites.

**pyrefly's interpreter path is load-bearing.** Serena answers `workspace/configuration` with `pythonPath` set
to its own interpreter (`solidlsp/language_servers/pyrefly_server.py`), which holds neither the workspace
members nor their dependencies. With the one-line `[tool.pyrefly]`, a definition of `DecisionRecord` from the
crawler lands in `packages/matching/src/catalog_matching/engine.py` and the ABC rename gives 75 / 12; without
the table (`[tool.mypy]` and `[tool.pyright]` still present), the same definition stays on the import line, a
third-party import resolves to `null`, and the rename gives 1 / 1. pyrefly does not discover `./.venv` alone.

**pyrefly's first rename is partial in the default indexing mode.** Serena declares pyrefly ready when no
`$/progress` token is active; the only token pyrefly emits, `Pyrefly: Rechecking 0/0`, begins and ends at 13 to
18 ms, before indexing. The ABC rename sent at that instant, without retry, on 5 fresh processes per mode:

| Indexing mode | First rename | Same process, 5 s later |
|---|---|---|
| default | 1 / 1 on 5 runs of 5 (the declaration, a valid `WorkspaceEdit`) | 75 / 12, 5 of 5 |
| `--indexing-mode lazy-blocking` | 75 / 12 on 5 runs of 5 (the request blocks, about 275 ms) | 75 / 12, 5 of 5 |

A trace with one rename every 50 ms reads 1 / 1 until 0.242 s and 75 / 12 from 0.292 s. Serena's retry covers
the `-32800` and `-32801` errors only, so a partial answer is applied as it comes.

**Memory, like for like.** pyrefly 1.4.0 with the one-line configuration: 199 MiB process, 235 MiB with its
`uvx` parent; basedpyright 1.40.2: 297 MiB tree after one rename, 422 to 432 MiB after the full sequence. Section
3.5's 142 MiB and 4.3's 144 and 201 MiB are pyrefly's process alone, while 4.4's 477.2 MiB is basedpyright's
tree: compared on one basis, pyrefly takes about half.

**Axis II, corrections** (ty 0.0.89 with `[tool.ty.src] include`, mypy 2.3.1): mypy's eight runs give
`Success` over 333 files in 12.58 to 12.69 s cold. ty's default levels give 38 errors and 1 warning (the table
of section 7 said 39 and 0); 37 of the 39 fall on the ignore lines, which become 39 with the strict block, so
"39 of its 55" holds for the strict run only. Totals move with the version (0.0.25: 65 default, 69 strict;
0.0.87 and 0.0.89: 39 and 55), the mechanism does not: `type: ignore[...]` codes without a `ty:` prefix are
skipped by design (ty's `docs/suppression.md`), and no setting makes ty read a mypy code. A combined bracket
`# type: ignore[arg-type, ty:invalid-argument-type]` fails mypy `--strict` (`Unused "type: ignore[ty:...]"
comment`); the form both accept is two comments, `# type: ignore[arg-type]  # ty: ignore[invalid-argument-type]`.
A `ty:` code naming the wrong rule keeps the error and adds the warning. `--disallow-incomplete-defs` has no ty
rule either (section 7's row 2 already groups it). `--strict-equality` is covered inside `if` conditions by
`redundant-condition-strict`, opt-in, and not in a value position (`return number == text`), which is ty#576.

**Two ports declaring the same method** (2026-10-17, pyrefly 1.4.0 in `lazy-blocking` mode and pyright 1.1.414,
the same client, `run_overlap.py` and `overlap_repo.sh` beside it, raw answers in `out/overlap-*.txt`). On a
fixture of three variants, `A(ABC)` declaring an abstract `m`, `Impl` implementing it and `use(a: A, b: B, i:
Impl)` calling all three:

| Variant | pyrefly from `A.m` | pyrefly from `B.m` | pyrefly from `Impl.m` | pyright, any |
|---|---|---|---|---|
| v1, siblings `A(ABC)` and `B(ABC)`, `Impl(A, B)` | 4 sites, never `B.m` | 4 sites, never `A.m` | 2 | 2 |
| v2, `B(A)` redeclaring `m`, `Impl(B)` | 6, `B.m` included | 4, never `A.m` | 2 | 2 |
| v3, `B(A)` not redeclaring `m`, `Impl(B)` | 5, the `b.m()` call included | (no `B.m`) | 2 | 2 or 3 |

On the repository clone (`repo_ovl`, from the ABC clone above), `download_candidates` renamed and applied, then
`mypy` over the crawler's 222 files:

- **Two sibling ABCs** (`DownloadCatalogReader(ABC)` in `run_download_cycle.py`, `CatalogRepository(ABC)`, the
  adapter inheriting both): from the reader, pyrefly 12 sites in 4 files, never the repository port; from the
  repository port, 11 sites in 4 files, never the reader. Either way `mypy` fails, `Cannot instantiate abstract
  class "SqliteCatalogRepository" with abstract attribute "download_candidates"`, 8 errors in 8 files. pyright:
  3 sites from the reader, 1 from the repository port, `mypy` failing with 85 and 10 errors.
- **`CatalogRepository(DownloadCatalogReader)`**, the reader moved to `ports/catalog_repository.py` and its three
  reads no longer redeclared: pyrefly renames 14 sites in 6 files from the reader or from a call typed
  `CatalogRepository`, and `mypy` is clean. pyright: 3 sites from the reader, 2 from the call, `mypy` failing
  with 87 and 2 errors.

**pyrefly does not resolve one test module importing another** (2026-10-17, a `git clone --no-hardlinks` at
`1c28d20` with its own `uv sync --dev`, `[tool.pyrefly]` as D3 writes it). `uvx --from pyrefly==1.4.0 pyrefly
check packages/crawler/tests/application/test_run_download_cycle_loop.py` reports `missing-import` for
`tests.application.test_run_download_cycle` at line 16: the inferred import root is the
repository's, and no `packages/<pkg>` is one. The consequence, on `repo_ovl`'s second variant: the 14 sites
above leave out `_ShutdownDuringCycleCatalog.download_candidates` (`test_run_download_cycle_loop.py:124`),
which overrides `FakeCatalogReads`' through that import. `mypy` stays clean, the stale override being an extra
method, and only the test that needed it fails: `test_loop_breaks_when_shutdown_is_set_during_the_cycle`, a
`TimeoutError`, `1 failed, 5 passed`.
