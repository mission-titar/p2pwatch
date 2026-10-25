# Stub and spy libraries for the tests

Measured 2026-10-25, on `main` at `23854f28`, by throwaway probes outside the repository (Python 3.13, pytest 9.1,
pytest-asyncio strict mode, `mypy --strict`). Re-run before acting on it.

## The question

Can one typed way replace the hand-written stubs and spies of `packages/*/tests/fakes/`, so that a call no stub
expects fails the test? The ports are ABCs with sync and `async def` methods; the code under test often catches
`except Exception` at its boundaries.

## The doubles today

100 doubles: 16 fakes with a contract, 69 stubs and spies (19 stubs, 20 spies, 30 both), 5 sabotaged, 5 outside-system
servers, 1 loop, 4 others. Most stubs answer whatever the arguments, but most also record their calls, which the tests
assert. No `fix` commit traces a bug to a stub ignoring its arguments. Four doubles take `**arguments: Any`
(`FakeSourceReader`, `FakeCatalogFileReader`, both `FakeCommandRunner`).

Four spies are asserted as an exact ordered list of calls (both `FakeLogger`, `FakeNotifier`, `FakeMetricsRecorder`),
and amule's four boot spies append to one `actions` list shared with `FakeAmuleConfStore`, a fake.

## The candidates

"Strict" means an unexpected call raises something an `except Exception` cannot swallow, or fails the test afterwards.

| Candidate | Strict | Typed under mypy | Exact list of calls | Health |
|---|---|---|---|---|
| Hand-written stubs on an in-house `Answers[**P, R]` + `Journal` (~60 lines) | yes, a `BaseException` | stub yes; a spy's arguments are untyped tuples | yes | no dependency |
| decoy 2.6.0, v2 API | partial: a swallowed miscall fails at teardown under `-W error`; a never-stubbed method returns `None` silently | yes, no false positive | no | one maintainer, last release 2026-04-30 |
| decoy 2.6.0, `decoy.next` (v3 preview) | no: the warning fires at call time, swallowable | yes | no | preview, "not subject to semver", no v3 date |
| `decoy.next` + a `strict_mock` helper | yes: a catch-all stub per abstract method raising a `BaseException`, overridden by the test's stubs | yes, one `ast-grep-ignore` for its `getattr` | no | as above |
| `create_autospec(spec_set=True)` + `seal`, pytest-mock | no | no, `Any` | yes | stdlib, maintained |
| flexmock, mockito, doubles, pretend, mocksafe, tmock, testslide | at best an `Exception` or a teardown check | no, or false positives on ABCs | mostly no | several unmaintained |

The pyrefly of the gate checks imports only, so mypy alone holds a double's typing.

## Verdict

Postponed. The gain is small: the stubs already record their calls and mypy already checks their signatures against the
port. The in-house helper keeps one class per port, so it adds code; decoy removes code but rests on a preview API
and needs a strict helper of our own.
