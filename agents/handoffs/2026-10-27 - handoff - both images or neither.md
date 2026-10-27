# Handoff: a release publishes both images or neither

## State

Tier Direct, one branch `fix/release-publishes-both-images-or-neither` cut from `main` at `2c0679ba`, one pull request.
It changes only `release.yml`, not what an image ships: no release follows it on its own.

The session opened the backlog entry of the same name. `publish-manifest` ran each image's gates and its publication in
one matrix leg, with `fail-fast: false`: a failing `image-claims` or `applied-claims` on one image left the other's new
`latest` (or `main`) beside its own old one.

## What was built

- **`publish-manifest` split in three jobs**, named by their high-level action, no glossary word nor tool:
  - `audit-source-unaffected-cves`, no matrix, beside `validate`: `vex-source-claims` and `vex-claim-coverage`, which
    read only the source and ran once per leg before.
  - `audit-image-unaffected-cves`, one leg per image after `validate`: the amd64 SBOMs, aMule in the SBOM,
    `image-claims`, `applied-claims` on a tag; it uploads the SBOMs as `sbom-<package>`.
  - `publish`, one leg per image, needing both audits: manifest list, tags, signature, the three attestations of the
    SBOMs the audit wrote. A matrix job fails when any leg does, and a failed need skips its dependents.
- **`github-release` needs `publish`**; `validate.yml`, `SECURITY.md` and `AGENTS.md` name the new job.
- **The backlog entry is deleted.**

## Evidence

- `actionlint` 1.7.7: no finding but three shellcheck notes (SC2012, SC2046 twice), the same on `main`'s
  `release.yml`.
- `zizmor --offline`: the same finding classes as on `main`; `artipacked` (+2) and `self-repository` (+1) count the
  added checkouts and `setup-uv-env` uses. Neither tool runs in CI.

## Not validated

- **The tag path**: `applied-claims` in the new job and the `latest` tag wait for the next tag. The merge's push (#512,
  `97382e60`, release run 40489236337, `success`) validated the path where both audits pass: both audit legs, both
  `publish` legs, `github-release` skipped off a tag.
- **The failing path** (one audit red, no `publish` leg run) rests on GitHub's documented `needs` semantics, never
  observed here.

## Decisions

- **Tier Direct**, by the operator: one block, `release.yml` only, no operator-facing surface.
- **Tags stay in `publish`**, not deferred to a later job after both signatures: the entry's case is a failing gate,
  which the split covers; an infrastructure failure halfway through `publish` is rerun.
- **Job names**, by the operator: the action a reader sees in the Actions view, without "VEX", "claim" or a tool;
  "unaffected CVEs" is the `not_affected` status in plain words, "exemption" implying a dispensed real flaw.

## Next

The backlog, "A copy before a migration that rewrites rows" first.
