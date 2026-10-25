# Handoff: the stub and spy survey, and two direct fixes

## State

Tier Direct, one branch `fix/dynamic-attribute-and-untyped-doubles` cut from `main` at `23854f28`, one pull request.
It ships nothing the image runs (a rule, two test doubles, documents), so no release follows it.

The session opened the backlog entry "Stubs and spies written with decoy" as a tier Spec lot, then stopped in
Discuss: the operator judged the gain too small for its cost today. The entry is rewritten without its library and
postponed ("A generic way to write the tests' stubs and spies"); the survey behind it is
`agents/reference/2026-10-25-stub-and-spy-libraries.md`.

## What was built

- **The survey** (Discuss, probes outside the repository): decoy's v2 and v3 preview APIs, a strict helper over
  `decoy.next`, an in-house `Answers` helper, and nine other libraries, graded on strictness, typing under
  `mypy --strict`, exact call lists, async and health. Findings and verdict in the reference note.
- **`no-dynamic-attribute` refuses `__getattr__`**: `type(mock).__getattr__(mock, name)` read an attribute by name
  past the rule. The rule had no test file; `ast-grep-tests/no-dynamic-attribute-test.yml` now holds its cases.
- **`FakeSourceReader` and `FakeCatalogFileReader` take their port's signature**, in place of `**arguments: Any`.

## Evidence

- The rule's new test failed on its two `__getattr__` cases before the fix (`FAIL no-dynamic-attribute
  .............MM..`), then passed (`14 passed; 0 failed`); `ast-grep scan` over the tree exits 0.
- A throwaway mypy probe calling `FakeSourceReader().read_source_count(search="x")` gave `Success: no issues found`
  before the retyping, `Unexpected keyword argument` after.
- `uv run poe check` exit 0 at the branch's tip (crawler `1615 passed`). Block: 102 changed lines, 6 files.

## Decisions

- Both `FakeCommandRunner` (amule, vex_checks) keep `**kwargs: Any`: they stand for `subprocess.run`, which
  `AGENTS.md` types `Callable[..., subprocess.CompletedProcess[str]]` at each site.

## Pitfalls

- `decoy.next` is less strict than decoy's v2 API: its miscall warning fires at call time, where an `except Exception`
  swallows it, and nothing checks at teardown.
- A dict literal handed to a `list[tuple[str, dict[str, object]]]` through a local needs the local annotated:
  `dict` is invariant, so mypy infers the narrower value type and refuses the append.

## Not validated

- Continuous integration at writing.

## Next

The operator reviews and merges the pull request. Another session takes the backlog, "A copy before a migration that
rewrites rows" first, since it blocks the next release.
