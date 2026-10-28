# Backlog

What the project intends to do next. One entry per improvement, at most two lines, stating
what changes and why it is wanted. Every entry stands alone: it carries its own link, so
deleting any other entry leaves it intact.

Not a changelog and not a record. An entry is **deleted** when it ships or when it is
dropped, never annotated with what became of it. The history is in git and in
`agents/handoffs/`.

An agent adds an entry only after the operator has agreed to it.

## Debt

- **Test quality** (lot 3 of the gate tooling umbrella): every unit test keeps unique coverage of its unit, the others are
  pruned, mutmut proving no detected mutant is lost. D3 to D5 and D13 to D15 of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`, lot order in D12.

- **Rows read by column name**: every reader of `persistence_sqlite` reads a column by its name,
  not its index, and every round-trip test seeds distinct values in fields of one type, so a shifted or swapped
  column fails the gate. Section 7 of `agents/specs/2026-10-28-typed-identifiers.md`.

## Must be done before the next release

- **The Grype scan back on p2pwatch at the v5 release**: one leg per image, `p2pwatch` and `p2pwatch-amule`, each with
  its versioned VEX and signed by `mission-titar/p2pwatch`, in place of v4's `mulewatch` leg. `.github/workflows/grype-scan.yml`.

## Features

- **Multi network**: a generic core driving one container per P2P client, renamed p2pwatch.
  Umbrella spec: `agents/specs/2026-10-08-multi-network-architecture.md`.
  - **Stage 5, new networks**: Soulseek (slskd), Direct Connect (AirDC++), Gnutella (gtk-gnutella),
    BitTorrent (Bitmagnet + qBittorrent); persistent and passive search ports with their first client, a `retry_after` on `SearchFailed` if slskd announces one, a free-space check per client output directory (the core's disk floor reads ed2k's only), `SourcePoint` refusing a contact point of another network than its file's. Stage 5 of `agents/specs/2026-10-08-multi-network-architecture.md`.

- **Sort the files view by first seen**: a `first_seen` key beside `last_seen`, timed on the node's catalog
  inside the container. Sort allowlist: `agents/specs/2026-06-22-webui-catalogue-design.md` §3.1.

- **The webui in the visitor's time zone**: UTC rendered, the browser converts each date with JavaScript; needs
  `AGENTS.md`'s "Python only" amended and a JS test chain. Section 6's "Adjacent backlog items" of `agents/specs/2026-10-13-append-only-source-points.md`.

## Technical improvements

- **Mutation testing in the gate**: mutmut run cold on a pull request's impact set, from the per-test coverage, so
  a test that stops detecting a fault fails the gate. D13 of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`.

- **Keyword-only calls**: ruff's `PLR0917` at one positional parameter and
  `kw_only=True` on every dataclass, so no call passes two values by position. Section 7 of
  `agents/specs/2026-10-28-typed-identifiers.md`.

- **Contract tests for the fakes of outside systems**: each suite run against the real system (amuled, apprise, GitHub,
  Gluetun) under the integration markers, never against a fake server. Section "Backlog" of `agents/specs/2026-10-25-fake-contract-tests.md`.

- **Every catalog table STRICT**, as `local.db`'s are: all of them rebuilt at once, so SQLite refuses a value of the
  wrong type; it costs a rebuild of the catalog's largest tables. D2 of `agents/specs/2026-10-28-micros-stamps.md`.

## Postponed

- **Adopt ty**, first as the gate's type checker in mypy's place, then as Serena's language server, once it reaches
  parity. Section "ty: the parity conditions" of `agents/specs/2026-10-17-serena-and-the-language-servers.md`.

- **A generic way to write the tests' stubs and spies**: one typed mechanism for all of them, where a call no stub
  expects fails the test, in place of a class per port. Candidates measured in `agents/reference/2026-10-25-stub-and-spy-libraries.md`.