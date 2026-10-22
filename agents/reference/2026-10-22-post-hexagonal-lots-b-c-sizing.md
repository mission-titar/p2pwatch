# Post-hexagonal corrections: what lots B and C start from

- Measured on `main` at `d4180cdf` (before lot A) on 2026-10-22 by Sonnet sizing agents, kept here because their
  reports lived in a session scratchpad. Lot A has since moved most paths (`application/ports/`, `use_cases/`,
  `steps/`, `composition/`, `tests/fakes/`): re-run every count and re-measure every block before acting on one.
- The cut, decided with the operator in lot A's Discuss: A (test tooling and layout, merged at `bc990263`), B (the
  names and the other hexagons' fixes), C (the crawler's design fixes). Ledger: `2026-10-22-post-hexagonal-audit.md`.

## Lot B: the names and the other hexagons

Scope: R3, R5, R8, N1 to N18 (N10's list in lot A's handoff), and H1 to H7, H10 to H15, R6, R6b and R11 outside the
crawler. Planned shape, agreed with the operator: every true symbol rename in **one mechanical block** (the exemption
has no size cap); normal blocks for what is no rename: the naming rules in `AGENTS.md` with the `record_`/`set_` verbs'
ast-grep rule (after the renames), N11, the prose (N15) and local names (N14), the logger names (R8, amule then the
crawler, after every module rename so names change once); then about five blocks for the other hexagons. About 12
blocks with the closing one.

- **R8 needs no migration precaution** (operator): `docs/migration-4x.md` lists port-sync's logger names; it only
  follows the code, like any doc.
- **H1 dissolves `amule_bump`'s `body` and `release`** (lot A's D6): their pure part to `domain/`, their reads of
  `RepoReader` into `BumpAmule`; they sit in `use_cases/` until then.
- Questions the sizing raised, to settle in B's Discuss:
  - **N17's rule reaches beyond the ledger's three renames**: `write_dockerfile`, `write_pull_request_body`,
    `write_step_outputs`, `write_amule_conf`, `write_violations` and `RunStateWriter.pause/resume/shut_down` start
    with neither `record_` nor `set_` (`git grep -nE "def (write_|pause|resume|shut_down|publish|mark_|save_)"` over
    the ports).
  - **N11 crosses operator surfaces**: `last_seen_at` and `last_progress_at` are SQL columns, `last_seen` a template
    key and the files view's `?sort=` key; renaming the columns is a migration, which waits for "A copy before a
    migration that rewrites rows". A Python-only rename can go in the mechanical block.
  - **N13**: `ed2k_hash` is also a column in 9 migrations; only the Python identifiers move.
  - **N12**: `*Deps`/`deps` is about 340 lines (270 in `run_download_cycle` and its test), `conn` 152; the 8 "repo
    failure" log messages are operator-visible text.
  - **R8**: 13 logger literals in `src` (`StdlibLogger("...")`, `getLogger("...")`), among them
    `p2pwatch.observability`; a module rename leaves a literal stale unless it is edited too.
  - **H7**: "one `run_command` type" cannot be shared across hexagons, which never import each other: a typed alias
    per hexagon, or a driven port.
  - **R11**: `amule_bump`'s `--body-file` default lives in the temporary directory, process state: neither a domain
    value nor a composition constant as the row says; a rule refusing a literal `default=` must spare
    `max(..., default=0)`.
  - **H2, H14** may be settled already by lot A's amule composition (one `build_command_line`): re-measure first.

## Lot C: the crawler's design fixes

Scope: A1 to A15, A17 (A16 was lot A's), R6, R6b, R6c, R7 and R11 for the crawler. Measured at about 16 blocks with the
closing one once the other hexagons went to B; no block is mechanical.

- Questions the sizing raised, to settle in C's Discuss:
  - **A13**: `${NAME}` interpolation in `crawler.yml` is lazy today (a disabled `download:` needs no variable); an
    eager pass in the adapter changes which unset variables are fatal and the errors' key paths.
  - **A8**: `RETRACTED_TIER = "retracted"` is stored in the `tier` column and ranked -1 but is not in `TIERS`; the
    row does not say where `DecisionTier` puts it.
  - **A2**: the role is read and written in one `BEGIN IMMEDIATE`, and `_LATEST_POINT` also drops session bytes and
    applies the max-age cutoff; the new `SourcePointReader` method must carry `read_at`, the source or name and the
    bytes, and the domain must own the cutoff.
  - **A17** touches about 70 files (456 `node_id` hits, `FileObservation(` built in 79 places): likely three blocks.
  - **A4** (the typed notification) does not fit one block; split by event kind, a transient double path lives for
    one block.
  - **A11**: `mule_api`'s `_PAGE_SIZE = 500` is another constant than the domain's `PAGE_SIZE`; do not merge them.
