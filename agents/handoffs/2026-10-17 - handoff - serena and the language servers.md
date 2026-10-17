# Handoff: Serena and the language servers, lot 2 of the gate tooling, Serena and test quality umbrella

Drafted by block 10 from its own report, for the closing block 20 to correct (holistic review or its waiver,
`BACKLOG.md`, the Wrap counts).

## State

Tier Spec lot, no operator-facing surface and no code: configuration and prose only. Spec
`agents/specs/2026-10-17-serena-and-the-language-servers.md`, approved by the operator on 2026-10-17; its
measurements are in `agents/reference/2026-10-16-python-language-server-bench.md`. The lot carries out U-D11 of
`agents/specs/2026-10-14-gate-tooling-and-test-quality.md`.

Two blocks, one stack cut from `main` at `fd9d681`:

| Block | Branch |
|---|---|
| 10 | `chore/serena-pyrefly` |
| 20 | `docs/serena-lot-wrap` |

Nothing of the stack is merged. Nothing the images ship changes, so Wrap (f) proposes no release.

## What was built

- **pyrefly is Serena's language server** (D1): `.serena/project.yml` lists `python_pyrefly` alone, with
  `ls_specific_settings.python_pyrefly` pinning `pyrefly_version: "1.4.0"` and `indexing_mode: lazy-blocking`.
- **`.serena/project.yml` is versioned** (D2): `.gitignore`'s `.serena` became `.serena/*` and
  `!.serena/project.yml`; `cache/`, `memories/`, `project.local.yml` and the nested `.gitignore` stay local. The
  file is Serena's own template with the two settings changed, hence most of the block's 210 counted lines.
- **`[tool.pyrefly] python-interpreter-path = "./.venv/bin/python"`** in the root `pyproject.toml` (D3);
  `[tool.pyright]`'s comment no longer names Serena.
- **AGENTS.md's Gotchas gain "Serena and its language server, pyrefly"** (D5): a port method renamed from the
  port and each implementer, the `tests.*` import gap, what no server renames, and the trust caveat.
- **`BACKLOG.md` gains two entries** (D6): adopt ty once it reaches parity, and the ports and composition
  architecture lot.

## Live verifications (block 10, 2026-10-17)

- **Acceptance 1**: `git ls-files .serena/project.yml` prints the path; `git check-ignore --no-index
  .serena/project.yml` exits 1, while `.serena/cache`, `.serena/project.local.yml`, `.serena/.gitignore` and
  `.serena/memories` are reported ignored.
- **Acceptance 2**, before the switch: Serena's child was `/usr/bin/uv tool uvx -p 3.13 --from pyright==1.1.403
  pyright-langserver --stdio`, and `find_declaration` of `build_ed2k_link` from
  `p2pwatch/domain/observability/policy.py` landed at `packages/matching/src/catalog_matching/ed2k_link.py:25`.
  After the operator's `/mcp` reconnect: the child reads `/usr/bin/uv tool uvx -p 3.13 --from pyrefly==1.4.0
  pyrefly lsp --indexing-mode lazy-blocking` (its own child `pyrefly lsp --indexing-mode lazy-blocking`), and the
  same `find_declaration` lands at the same line.
- **Acceptance 3**, `rename_symbol SqliteBackoffStateRepository/save_backoff_states` to `store_backoff_states`,
  each time from an empty `git status --porcelain`, reverted with `git restore .`, empty again:
  - pyright: "4 changes applied", 4 files, 9 sites. In `tests/application/test_search_tasks.py` only the
    `super().save_backoff_states(...)` call (line 94); `_SavesRecorded`'s override `def` (line 90) is left.
  - pyrefly: "4 changes applied", 4 files, 10 sites: the same nine plus the override's `def` at line 90.
  - Under both, the port (`ports/backoff_state_repository.py`), its double in
    `tests/ports/test_backoff_state_repository.py` and the use case's call in `application/search_tasks.py` are
    left: the structural edge of the first Gotcha.
- **Acceptance 4**: `uv run poe check` exit 0 at `9ac3d03`.
- **Acceptance 5** at block 10's tip: `git diff --name-only main...HEAD` lists `.gitignore`,
  `.serena/project.yml`, `AGENTS.md`, `BACKLOG.md`, `pyproject.toml` and the spec and bench report; `uv lock`
  printed "Resolved 64 packages" and left `uv.lock` untouched.

## Spec corrections

- **Acceptance 3's falsifier** (block 10, `bed3c51`, at the lead's request): "the file is absent from the
  pyrefly diff" could not fail, since pyright reaches `test_search_tasks.py` through the `super()` call. The
  expected observable and the falsifier are now the override's `def` line, marked `(Corrected 2026-10-17: ...)`.

## Pitfalls

- **A running Serena never re-reads `.serena/project.yml`.** The claude-code context exposes neither
  `activate_project` nor `restart_language_server` (an optional tool), and a dead language server is restarted
  from the in-memory configuration (`serena/ls_manager.py:166-208`), so killing the child respawns the old
  server. Only restarting the MCP server applies a change: `/mcp`, reconnect `serena`.
- **Every other running session keeps its old server until it reconnects**: at block 10, a Serena started on
  2026-10-16 by another session still ran pyright 1.1.403.

## Not validated

- An untrusted clone's fallback (D1's caveat: pyrefly 1.2.0 in the default mode) was read from Serena's source,
  not observed; this machine trusts `**`.
- The partial first rename that `lazy-blocking` avoids was measured by the bench (section 11), not re-measured
  through the live Serena.
- Whether a Serena upgrade rewrites the versioned `project.yml` (its template gains keys between versions).

## Wrap counts

For block 20 to fill: fix-backs, cascaded rebases, runs re-triggered, bodies called unreadable.

## Next

- Block 20: the operator decides on the holistic review's waiver (the spec names this lot one of
  one block), `BACKLOG.md` loses the lot's own entry, this handoff is corrected.
- Then lot 3 of the umbrella (test quality), which renames and deletes many symbols and so meets the new
  Gotchas first.
