---
paths:
  - "pyproject.toml"
  - "packages/*/pyproject.toml"
  - "tach.toml"
  - "**/Dockerfile"
---

# Package boundary

- **Package boundary:** which package imports which is the hexagon rule's (Hard rules, "Clean / Hexagonal"). `vex_checks`, `template_checks`, `coverage_checks` and `amule_bump` are dev/CI tooling, never installed in the prod image. `pytest_settings` is shared test configuration, not a hexagon: one module, declared in `tach.toml`, holding what every package's pytest run applies (the root's `dev` group installs it, its `pytest11` entry point loads it), outside vulture's scope like the tests, and never installed in the prod image.
