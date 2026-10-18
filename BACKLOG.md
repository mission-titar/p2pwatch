# Backlog

What the project intends to do next. One entry per improvement, at most two lines, stating
what changes and why it is wanted. Every entry stands alone: it carries its own link, so
deleting any other entry leaves it intact.

Not a changelog and not a record. An entry is **deleted** when it ships or when it is
dropped, never annotated with what became of it. The history is in git and in
`agents/handoffs/`.

An agent adds an entry only after the operator has agreed to it.

- **Multi network**: a generic core driving one container per P2P client, renamed p2pwatch.
  Umbrella spec: `agents/specs/2026-10-08-multi-network-architecture.md`.
  - **Stage 5, new networks**: Soulseek (slskd), Direct Connect (AirDC++), Gnutella (gtk-gnutella),
    BitTorrent (Bitmagnet + qBittorrent); persistent and passive search ports with their first client, a `retry_after` on `SearchFailed` if slskd announces one, a free-space check per client output directory (the core's disk floor reads ed2k's only). Stage 5 of `agents/specs/2026-10-08-multi-network-architecture.md`.

- **Sort the files view by first seen**: a `first_seen` key beside `last_seen`, timed on the node's catalog
  inside the container. Sort allowlist: `agents/specs/2026-06-22-webui-catalogue-design.md` §3.1.

- **A copy before a migration that rewrites rows** (required before the next release): the runner copies the
  catalog with `VACUUM INTO` first. Design: section 9 of `agents/specs/2026-10-13-append-only-source-points.md`.

- **The webui in the visitor's time zone**: UTC rendered, the browser converts each date with JavaScript; needs
  `AGENTS.md`'s "Python only" amended and a JS test chain. Section 6 of `agents/specs/2026-10-13-append-only-source-points.md`.

- **Every stamp an integer of microseconds since the epoch**, as the catalog's points already are: the ISO-8601 TEXT
  stamps left in both databases converted; the catalog's waits for the copy before a migration that rewrites rows. D12 of `agents/specs/2026-10-14-monotonic-clock.md`.

- **Hexagonal architecture**: rings read from the paths, ports as ABCs, six hexagons that never import one another,
  enforced by tach and ast-grep. Umbrella spec: `agents/specs/2026-10-18-hexagonal-architecture.md`, lots in D18.
  - **Lot 1, foundations**: the composition wired without factories and tested in integration, every package moved
    to the ring paths and explicit subcommands, then the gate with its deprecated edges. D11 to D18.
  - **Lot 2, the `p2pwatch` hexagon**: the self-reconnecting session, the logging port, the webui's read side and `merge`
    behind use cases, the ports as ABCs split into roles. Inherits the two sections D20 of the umbrella spec names.
  - **Lot 3, the other five hexagons**: their I/O behind ports, their tests off `monkeypatch`, and the documentation
    left over. D18 of the umbrella spec.

- **Adopt ty**, first as the gate's type checker in mypy's place, then as Serena's language server, once it reaches
  parity. Section "ty: the parity conditions" of `agents/specs/2026-10-17-serena-and-the-language-servers.md`.

- **Test quality** (lot 3 of the gate tooling umbrella): every unit test keeps unique coverage of its unit, the others are
  pruned, mutmut proving no detected mutant is lost. D3 to D5 and D13 to D15 of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`, lot order in D12.

- **Mutation testing in the gate**: mutmut run cold on a pull request's impact set, from the per-test coverage, so
  a test that stops detecting a fault fails the gate. D13 of `agents/specs/2026-10-14-gate-tooling-and-test-quality.md`.

- **The logic-free template guard on Jinja's syntax tree**, not on the text, so the fallbacks and filtered loops it
  misses today move into the views. Section 7 of `agents/specs/2026-10-15-gate-tooling.md`.

- **Contract tests for the fakes**: one suite per port, run against the fake and the real adapter, so a fake cannot
  drift from what it stands for. Section 7 of `agents/specs/2026-10-15-gate-tooling.md`.
