---
paths:
  - "docs/**"
---

# The documentation site

- **`docs/` is the Zensical root and is published in full**: every `.md` under it becomes a page on https://mission-titar.github.io/p2pwatch/, because Zensical builds every file in `docs_dir` whether or not the nav references it. Anything that should not be published goes in `agents/` (specs, plans, handoffs, reference notes), never in `docs/`. The site is built by `uv run poe docs-build`, which passes `--strict` so a broken link or a dead anchor fails the build instead of shipping silently.
