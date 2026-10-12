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

- **Search observations as time ranges**: ranges updated in place instead of one row per sighting, `node_id`
  moved from the variant to the range, as stage 4 does for sources. Current model: `agents/specs/2026-10-09-stage1-generic-identity.md`.

- **Merge diverged copies of one node's catalog**: `merge` refuses, on every attempt, a copy taken before the node's
  catalog was restored or replaced. Limit and fix options: D6 of `agents/specs/2026-10-11-stage4-source-history.md`.

- **Sort the files view by first seen**: a `first_seen` key beside `last_seen`, timed on the node's catalog
  inside the container. Sort allowlist: `agents/specs/2026-06-22-webui-catalogue-design.md` §3.1.

- **Paginate the file detail timeline** (low priority): it renders every sighting, 12.9 MB for the
  node's heaviest file (38,593 rows). Measured in `agents/handoffs/2026-10-05 - handoff - shared observation reads.md`.
