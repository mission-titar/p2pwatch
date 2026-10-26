# The VEX claims Grype applies

- Date: 2026-10-26. Status: approved by the operator, 2026-10-26, after two reviews (`applied-claims-spec-review`).
- Tier: Spec. Origin: pull request #504 and the Discuss of 2026-10-26.
- Size: three blocks and the closing one.
- Measured on `main` at `0d719901`. Details in appendix A, measurements in appendix B.

## The problem

Our VEX files claim some CVEs `not_affected`, and Grype applies each claim to the packages it names. Until #504, the
two Python claims named `pkg:generic/python`. No package of our Debian images has that name, so Grype applied the
claims to nothing, and both CVEs stayed in the scan. No check noticed.

Today, `stale-claims` only flags a claim whose CVE Grype no longer reports. A claim that Grype still reports but does
not apply passes every check.

## What changes

1. **A new check, `applied-claims`, replaces `stale-claims`.** It runs Grype with the VEX and checks each claimed CVE.
   Grype must report the CVE, or the claim is stale. Grype must suppress every match of the CVE, or the claim is not
   applied.
2. **It blocks a release tag.** In `release.yml`, it runs after `image-claims` and before anything is published. It
   does not run on a push to `main`. The daily scan runs it too, as SARIF that never fails the workflow.
3. **CI installs Grype and Syft verified.** Two composite actions, `install-grype` and `install-syft`, check each
   binary's signature with cosign. They replace every unverified install we have today.

What an operator sees:

- At a release tag, an image with a stale or unapplied claim publishes nothing. The other image still publishes, as
  with `image-claims` today.
- The daily scan's SARIF category `vex-stale-claims-<package>` becomes `vex-applied-claims-<package>`. No alert is open
  under the old name, so none is orphaned.
- Nothing changes on a node.

## Decisions

- **D1. Grype decides whether a claim applies.** Why: Grype matches a claim by its own rules, on the package and on
  the image. Asking Grype catches a wrong package name, a package left out and a wrong image name. Comparing the VEX
  with the SBOM ourselves would catch only the first, and could drift from Grype.
- **D2. A stale claim and an unapplied claim are both errors.** Why: a VEX that lies and a VEX that suppresses
  nothing are equally bad in a signed attestation (the operator). A claim applied to some packages of its CVE and not
  others counts as not applied, because each of our claims covers one upstream source whose packages share its code.
- **D3. The check blocks a release tag only.** Why: `release.yml` also runs on every push to `main`. There, a change
  in Grype's database, or its outage, would block the `main` images of every merge, whatever the merge changed (the
  operator). Cost accepted: a database change on a release day holds the tag until the VEX is fixed.
- **D4. Names**, chosen by the operator: the subcommand `applied-claims`, the use case `CheckAppliedClaims`, its port
  `AppliedClaimsChecker`, its report `AppliedClaimsReport`. The scanner returns a `VulnerabilityScan` with
  `found_advisory_ids` (every match) and `unsuppressed_advisory_ids` (the matches the VEX left), a subset. Why: each
  field answers one question of D2. No glossary line, since `claim` is already there.
- **D5. One SARIF rule id, `unapplied-vex-claim`.** Why: the reporter writes one rule per check, as `image-claims`
  does, and the message tells the two problems apart.
- **D6. Grype and Syft are installed by our own actions, verified with cosign.** Why: the anchore actions we use are
  pinned by SHA, but they fetch the installer at a tag, which can move, and they verify no signature. The job that
  signs our images runs one of them. One pin per tool also ends the two Grype versions the daily scan runs today.
  Cost accepted: Dependabot no longer bumps these two tools; we bump them by hand.
- **D7. No Grype run on a pull request** (the operator). Why: it would need SBOMs of the pull request's images, and it
  would turn red on unrelated pull requests whenever Grype's database changes. The VEX changes a few times a year, and
  the release tag catches an error before anything is signed.

## Acceptance

Each behaviour test is watched failing before its implementation, its failure line in the block report.

Block 10, the rename:

1. `python -m vex_checks applied-claims` does what `stale-claims` did, and `stale-claims` is refused as an invalid
   choice.

Block 20, the verified installs:

2. No workflow uses `anchore/scan-action` or `anchore/sbom-action`, and only the two composite actions fetch an
   installer, at a commit.
3. Each action refuses a binary it cannot verify: run once with a wrong certificate identity, its step fails on
   cosign's error. A normal install logs `signature verification succeeded`.
4. After the merge, `validate` and `release.yml`'s `publish-manifest` are green, and the aMule SBOM still lists aMule.

Block 30, the check:

5. The use case's tests: a claim Grype does not find is stale; a claim with an unsuppressed match is not applied, even
   if other matches are suppressed; a fully suppressed claim passes; an unreadable VEX fails before Grype runs.
6. The scanner's tests read Grype's JSON as appendix A describes, including a report with no `ignoredMatches`.
7. Against real Grype, on the `main` images: `main`'s VEX before #504 fails, naming both Python CVEs not applied; the
   current VEX passes; a claim for a CVE Grype does not report fails, named stale.
8. In `release.yml`, the check and its Grype install run only on a tag. After the merge, `publish-manifest` shows
   both steps skipped and stays green.
9. No sentence about staleness being left out of the release remains in `release.yml` or `SECURITY.md`.

Every block: `uv run poe check` exits 0.

## Blocks

| Block | Branch | Content | Estimate |
|---|---|---|---|
| 10 | `refactor/applied-claims-name` | the rename of `stale-claims` to `applied-claims`, behaviour unchanged | about 104 lines, 13 files |
| 20 | `chore/verified-anchore-tools` | D6: the two actions, and every Grype or Syft install through them | about 119 lines, 5 files |
| 30 | `feat/applied-vex-claims` | D1 to D5: the new check, the release gate, `SECURITY.md`; drafts the handoff | about 319 lines, 13 files |
| 40 | `docs/applied-vex-claims-closing` | the holistic review's fixes, the new backlog entry, the handoff | a few lines |

Why four blocks where the Discuss planned one: as one block, the work reached 19 files, and the use case renamed and
rewritten at once would have counted twice. So the rename goes first, alone. D6 came later, on the operator's
question, and changes how CI installs tools, apart from the check itself. Estimates by agent `applied-claims-estimate`.

Cut from `main` at `cc57f84d` or later, where #504 is merged.

## Not in this lot

- **"The Grype scan back on p2pwatch at the v5 release"** stays open. That lot adds the daily scan's two v5 legs,
  which will use the category this lot names.
- **"Contract tests for the fakes of outside systems"** stays open. Its scope is amuled, apprise, GitHub and Gluetun;
  here, acceptance 7 checks the scanner against the real Grype.
- **New backlog entry, "A release publishes both images or neither"** (the operator), added by the closing block. At a
  tag, each image publishes on its own, so one failing image leaves the other's new `latest` beside its own old one.
  `image-claims` already does this; this lot adds a second way to reach it.

## Accepted limits

- D6 trusts more than GitHub: Sigstore, which signs the checksums; anchore's own release workflow, since a signature
  proves where a binary comes from, not that it is sound; and Grype's database, fetched unsigned at each run, which
  can bias the scan but runs no code.
- A claim that Grype matches through its `aliases` is out of scope: none of ours has any.

## Not validated before merging

- The release steps run only on a tag, first at v5's.
- The daily scan runs the check on `main` after the merge. It still scans v4's `mulewatch`, whose attested VEX names
  `pkg:generic/python`, so it should report both Python claims not applied until the v5 legs replace it. Expected,
  not measured.

## Appendix A. Details for the blocks

**Reading Grype's JSON (block 30).** The scanner runs `grype sbom:<sbom> --vex <vex> -o json`.

- `unsuppressed_advisory_ids` is the CVE ids of `matches`.
- `found_advisory_ids` adds the ids of `ignoredMatches` whose `appliedIgnoreRules` has an entry of namespace `vex`.
- A match ignored by another rule counts in neither, as in today's scan without `--vex`.
- Grype leaves `ignoredMatches` out when it ignores nothing; it reads as empty.
- `--show-suppressed` changes nothing in the JSON, so it is not passed.
- The use case reads the VEX before running Grype, so a missing VEX is named by `OpenVexReader`. Grype would fail on
  it with an error that names the SBOM.
- `VulnerabilityScan` lives in `domain/vulnerability_scan.py`, since a driven read port returns domain types only. The
  port becomes `VulnerabilityScanner.scan_sbom(sbom_path, vex_path) -> VulnerabilityScan`.

**The release step (block 30).** In `publish-manifest`, after `image-claims`: `install-grype`, then
`python -m vex_checks applied-claims` without `--sarif`, both under `if: startsWith(github.ref, 'refs/tags/v')`. The
comment that keeps staleness out of the release goes, and so do the matching sentences of `SECURITY.md`.

**The composite actions (block 20).** Each one:

1. installs cosign with `sigstore/cosign-installer`, pinned by SHA;
2. downloads the tool's `install.sh` at the commit of the pinned release's tag into a file, so a cut download never
   runs;
3. runs it with `-v` and `DOWNLOAD_TAG_INSTALL_SCRIPT=false`, then puts the binary on `PATH`.

With `-v`, cosign verifies the release's `checksums.txt` against the identity
`anchore/<tool>/.github/workflows/release.yaml@refs/heads/main`, then the binary is checked against it. Without
`DOWNLOAD_TAG_INSTALL_SCRIPT=false`, the script fetches the tag's `install.sh` from `get.anchore.io` and runs that one
instead, so the pinned script verifies nothing (measured by the review; `sbom-action` sets the variable for the same
reason). The pinned version is a release at least two weeks old; its `install.sh` handles both signature formats.

**What the actions replace (block 20).**

- `grype-scan.yml`'s `curl | sh` step, which ran a pinned script without `-v`.
- `anchore/scan-action`, replaced by `grype sbom:<sbom> --vex <vex> -o sarif --file <f>`. No `--fail-on`, which makes
  Grype exit 2 on a finding. The review measured the same rule ids and fingerprints as `scan-action`'s, so the 365
  open alerts are not duplicated.
- `anchore/sbom-action` in `validate.yml`, for the aMule SBOM of a local image.
- `anchore/sbom-action` twice in `release.yml`, replaced by one
  `syft scan registry:<ref> -o syft-json=<f> -o cyclonedx-json=<f>`, as `sbom-action` reads a registry when given
  credentials. `SYFT_SELECT_CATALOGERS` is kept, and the credentials go in `SYFT_REGISTRY_AUTH_USERNAME` and
  `SYFT_REGISTRY_AUTH_PASSWORD`.

## Appendix B. Measurements

On 2026-10-26, Grype database built 2026-10-26T06:38:44Z.

- SBOMs: `docker run --rm -v $S:/out anchore/syft:v1.42.3 <image> -o syft-json=/out/<name>.syft.json -q`, with
  `-e SYFT_SELECT_CATALOGERS=+sbom-cataloger` for aMule.
- Scans: `docker run --rm -v $S:/out anchore/grype:v0.118.0 sbom:/out/<name>.syft.json --vex /out/<vex> -o json`, and
  the same with `v0.115.0`.

Results:

- Both Grype versions agree on both images. With `main`'s VEX before #504, the two Python CVEs are unsuppressed on
  `python3.13`, `python3.13-minimal`, `libpython3.13-minimal` and `libpython3.13-stdlib`. With #504's VEX, both are
  suppressed by a `vex` rule, as are aMule's CVE-2006-2691 and CVE-2006-2692. No match is ignored by another rule.
- An SBOM made from the amd64 image's digest, with no tag, as the release makes it: #504's claims apply, 0 Python
  matches left, 8 suppressed.
- aMule SBOM with #504's VEX, without `--show-suppressed`: 345 `matches`, 10 `ignoredMatches`. Crawler SBOM with
  `main`'s VEX, where nothing is ignored: no `ignoredMatches` key at all.
- Open code scanning alerts (`gh api --paginate`): 365, all under `grype-mulewatch`.
- `release.yml` triggers on `push: branches: [main]` and on `v*` tags, and `publish-manifest` has no `if:`.
