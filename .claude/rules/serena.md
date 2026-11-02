---
paths:
  - "packages/**/*.py"
---

# Serena and its language server, pyrefly

Sections cited from `agents/reference/2026-10-16-python-language-server-bench.md`.

- **A port method is renamed from the port.** The ports are ABCs, and renamed from a base, pyrefly reaches the overrides; renamed from an override, it never climbs to the base (bench 11).
- **Check each rename's diff before the next one**: renames run back to back can reach a few references each and write some edits at shifted offsets; then `git grep -w` the old name.
- **pyrefly resolves a package's `tests` only through the package's own `[tool.pyrefly]`** (`search-path = ["src", "."]`; its sub-configs cannot change import paths). Without it, `pyrefly check` from the root cannot find `tests.fakes` (23 errors in five packages at lot A's base), and the audit's trial saw a rename from a port miss the overrides in `tests` (9 of 12 sites), while mypy stays green, since a stale override becomes an extra method; `pyrefly-check` fails a package that lacks it (bench 11, lot A's spec D1).
- **Never renamed completely by any server**: a pytest fixture's uses in the test bodies, an attribute only a Jinja template reads, a name inside a string (`__all__` included, under pyrefly) and a `dataclasses.replace` keyword (bench 3.1, 5.7).
- **`.serena/project.yml` pins pyrefly 1.4.0 in `lazy-blocking` mode only in a project Serena trusts** (`trusted_project_path_patterns` in the user's global Serena config). Untrusted, Serena starts its own pyrefly 1.2.0 in the default mode, whose first rename after start is partial (bench 11).
