---
paths:
  - "packages/*/src/**"
  - "packages/*/tests/**"
---

# Coverage by own tests (`_unit-coverage-check`)

- **A body the process runs once is credited to one test at most.** A function called at import is credited to none (pytest-cov records collection under the empty context), so its module's own tests must call it. A `functools.cache`d function, module state initialised lazily, or a session- or module-scoped fixture is credited to whichever test runs it first, so its module's own tests pass or fail on test order and selection: keep such state out of `src`, or have the module's own tests reset it (`cache_clear()`).
- An `@abstractmethod`'s body is its docstring alone (a `...` or `pass` under it is a line no test runs).
- A `case _: assert_never(x)` arm (the "unreachable default" of a `match` over a closed tagged-union) needs `# pragma: no cover`: it is unreachable by design but the branch counter doesn't know that.
