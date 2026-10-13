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

- **A monotonic clock for in-memory intervals and deadlines**, the wall clock kept for stamps, and a wait from a
  persisted time capped by its policy's maximum. Section 8 of `agents/specs/2026-10-13-append-only-source-points.md`.

- **Descriptive names**: find the symbols whose names say little (`what`), rename them consistently, and if
  possible add a lint rule or an agent guideline that prevents them. No spec yet: https://github.com/mission-titar/p2pwatch/pull/198#discussion_r4261141305.
