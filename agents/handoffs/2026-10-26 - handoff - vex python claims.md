# Handoff: the VEX's Python claims applied by Grype

## State

Tier Direct, one branch `fix/vex-python-claims-debian-purls` cut from `main` at `0d719901`, one pull request. It
ships the backlog entry "The VEX's Python claims applied by Grype", deleted from `BACKLOG.md`. The VEX is attested on
each image at release, so the fix reaches the scan with the v5 release, whose Grype legs read the new images' VEX
("The Grype scan back on p2pwatch at the v5 release").

## What was built

- **CVE-2025-15366 (`imaplib`) and CVE-2025-15367 (`poplib`) name the Debian packages Grype reports them on**, in both
  VEX files: `pkg:deb/debian/python3.13`, `python3.13-minimal`, `libpython3.13-minimal` and `libpython3.13-stdlib`,
  versionless, in place of `pkg:generic/python`. That PURL dates from the Alpine-era image, whose Python Syft
  catalogued as a binary; since both images moved to Debian's `python3`, it matched no package and the claims
  suppressed nothing. Each statement's and each document's `timestamp` moved to 2026-10-26, each `version` up by one.

## Evidence

Syft 1.42.3 over `ghcr.io/mission-titar/p2pwatch:main` and `p2pwatch-amule:main` (Syft-JSON, the aMule one with
`SYFT_SELECT_CATALOGERS=+sbom-cataloger`), Grype 0.115.0 as `grype-scan.yml` pins it, `--show-suppressed`, 2026-10-26:

- With `main`'s VEX, each image: 8 matches of the two CVEs, 0 ignored, on the four packages above at
  `3.13.5-2+deb13u5`.
- With the branch's VEX, each image: 0 matches, 8 ignored by `{"namespace":"vex","vex-status":"not_affected"}`. On
  the aMule image the ignored advisories are exactly CVE-2006-2691, CVE-2006-2692, CVE-2025-15366, CVE-2025-15367:
  its other claims still apply.
- `python -m vex_checks claim-coverage` exit 0; `image-claims` exit 0 on both images' SBOMs.
- `uv run poe check` exit 0 (crawler `1634 passed`).

## Pitfalls

- **A subcomponent PURL that names no package of the SBOM fails silently**: Grype keeps reporting the CVE, so
  `stale-claims` sees nothing wrong, and no check compares a claim's subcomponents to the SBOM.
- **The package names carry the Python version**: when Debian's `python3` moves past 3.13, these claims stop
  matching and both CVEs show again in Code scanning, visibly.

## Not validated

- Continuous integration at writing.
- The scan of the released v5 images, which reads their attested VEX.

## Next

The operator reviews and merges the pull request. Then the backlog, "A copy before a migration that rewrites rows"
first, since it gates the v5 release.
