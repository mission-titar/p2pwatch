# Handoff: the VEX claims Grype applies

Drafted by block 30 from the lot's block reports (#505, #506) and its own, for the closing block 40 to correct with
the holistic review.

## State

Tier Spec lot. Spec `agents/specs/2026-10-26-applied-vex-claims.md` (approved by the operator 2026-10-26, after the
review `applied-claims-spec-review`). Its origin is #504, which fixed the two Python claims that named
`pkg:generic/python` and so applied to nothing, while every check passed.

One stack cut from `main` at `cc57f84d` (#504 merged), which had not moved when block 30 was written (`git fetch`,
2026-10-26). Four blocks with the closing one, as the spec planned. No split, no exemption.

| Block | Pull request | Branch |
|---|---|---|
| 10 | #505 | `refactor/applied-claims-name` |
| 20 | #506 | `chore/verified-anchore-tools` |
| 30 | block 30's | `feat/applied-vex-claims` |
| 40 | the closing block's | `docs/applied-vex-claims-closing` |

Not merged at writing. The lot changes no image: `vex_checks` is CI tooling, and the workflows change how CI installs
Grype and Syft and gates a release. A lot that ships nothing in an image proposes no release (`agents/workflow.md`,
Wrap (f)).

## What was built

- **The rename** (block 10, D4): the subcommand `stale-claims` became `applied-claims` (the old name refused as an
  invalid choice), with its driving port `AppliedClaimsChecker`, its report `AppliedClaimsReport`, its use case
  `CheckAppliedClaims` and its double; the daily scan's SARIF category became `vex-applied-claims-<package>`. Behaviour
  unchanged.
- **The verified installs** (block 20, D6): two composite actions, `.github/actions/install-grype` (Grype v0.120.1)
  and `install-syft` (Syft v1.54.1), each installing cosign, fetching the tool's `install.sh` at the release tag's
  commit into a file, and running it with `-v` and `DOWNLOAD_TAG_INSTALL_SCRIPT=false`. They replace
  `anchore/scan-action`, `anchore/sbom-action` (in `validate.yml` and twice in `release.yml`, now one
  `syft scan registry:...` with two outputs) and the daily scan's `curl | sh`. Dependabot no longer bumps either tool.
- **The check** (block 30, D1, D2, D4, D5): the driven port is `VulnerabilityScanner.scan_sbom(sbom_path, vex_path)
  -> VulnerabilityScan`, the value in `domain/vulnerability_scan.py` with `found_advisory_ids` and
  `unsuppressed_advisory_ids`. `GrypeVulnerabilityScanner` runs `grype sbom:<sbom> --vex <vex> -o json`: `matches` are
  unsuppressed, `ignoredMatches` with an `appliedIgnoreRules` entry of namespace `vex` are found too, a match ignored by
  another rule counts in neither, and a report with no `ignoredMatches` reads as empty. `CheckAppliedClaims` reads the
  VEX first, then flags each claim `stale: Grype does not report it` or `not applied: Grype leaves a match
  unsuppressed`, both under the SARIF rule `unapplied-vex-claim`.
- **The release gate** (block 30, D3): in `release.yml`'s `publish-manifest`, after `image-claims`, `install-grype`
  then `python -m vex_checks applied-claims` without `--sarif`, both under
  `if: startsWith(github.ref, 'refs/tags/v')`. The comment that kept staleness out of the release is gone, and
  `SECURITY.md` describes the check as a release hard-fail on a tag only.

## Acceptance

1. Block 10: before the rename, `assert "invalid choice: 'stale-claims'" in ...` failed; after,
   `python -m vex_checks stale-claims --sbom x --vex y` exits 2 with `invalid choice: 'stale-claims'`.
2. Block 20: `git grep -n "anchore/scan-action\|anchore/sbom-action" -- .github` prints nothing; `install.sh` and
   `get.anchore.io` appear only in the two `action.yml`.
3. Block 20, locally with cosign v3.0.6: a normal install logs `signature verification succeeded`; a wrong identity,
   through a `COSIGN_BINARY` wrapper, fails both tools on `failed to verify certificate identity: no matching
   CertificateIdentity found`.
4. Waits for CI and the merge (`validate`, `publish-manifest`, aMule in the SBOM). Block 20 checked locally that both
   SBOMs of `p2pwatch-amule:main` carry `pkg:generic/amule@3.1.0`.
5. Block 30, `test_check_applied_claims.py`, each watched failing on the old logic over the new signature:
   - stale: `problems: (ClaimProblem(advisory_id='CVE-B', message='no longer reported by Grype'),) !=
     (ClaimProblem(advisory_id='CVE-B', message='stale: Grype does not report it'),)`;
   - not applied though another match is suppressed: `problems: () != (ClaimProblem(advisory_id='CVE-B',
     message='not applied: Grype leaves a match unsuppressed'),)`;
   - an unreadable VEX: `assert [(PurePosixPath('/tmp/sbom.syft.json'),
     PurePosixPath('/repo/security/crawler.vex.openvex.json'))] == []`, the scanner run before the reader raised;
   - the SARIF rule id `unapplied-vex-claim`; a fully suppressed claim passes.
6. Block 30, `test_grype_vulnerability_scanner.py`, over the old parsing: a VEX-ignored match not found
   (`found_advisory_ids: frozenset({'CVE-1'}) != frozenset({'CVE-1', 'CVE-2'})`), a match ignored by the VEX among
   other rules not found (`assert frozenset() == {'CVE-2'}`), four malformed `ignoredMatches` shapes `DID NOT RAISE
   BrokenInputError`. A report with no `ignoredMatches` is the shape of the matches-only tests.
7. Block 30, against real Grype v0.120.1 (`anchore/grype:v0.120.1` behind a `grype` wrapper on `PATH`, database built
   2026-10-26T06:38:44Z), on SBOMs made by `anchore/syft:v1.42.3` from `p2pwatch:main` (`sha256:3920aa5a...`) and
   `p2pwatch-amule:main` (`sha256:155f6624...`, with `+sbom-cataloger`):
   - VEX before #504 (`cc57f84d^`): exit 1 on both images, `CVE-2025-15366` and `CVE-2025-15367` each `not applied:
     Grype leaves a match unsuppressed`;
   - current VEX: exit 0 on both images;
   - the crawler's VEX plus a claim for `CVE-1999-0001`: exit 1, `CVE-1999-0001: stale: Grype does not report it`.
8. Waits for the merge: `publish-manifest` on `main` should show both new steps skipped and stay green.
9. Block 30: `grep -n -i "stale\|prune" .github/workflows/release.yml SECURITY.md` prints only `SECURITY.md`'s two
   lines naming a stale claim as a failure.
10. Every block's report: `uv run poe check` exit 0 at its tip.

## The holistic review's findings

For the closing block.

## Departures from the spec

- Block 20: the daily scan's Grype step passes `--vex "$VEX"`, the leg's VEX, where `scan-action` named
  `/tmp/vex.openvex.json`, that leg's value today. The explicit `Install cosign` steps of `grype-scan.yml` and
  `release.yml` stay, though the actions install cosign too.
- Block 30: the messages name the problem first (`stale: ...`, `not applied: ...`), since D5's one rule id leaves the
  message to tell them apart; `SECURITY.md`'s intro said all four checks ran as a PR job, where `pr.yml` runs only the
  source claims and `claim-coverage`: corrected in passing (class 1). The daily scan's step was renamed after the check.

## Class 1 fixes

- Block 30: `SECURITY.md`'s sentence on which checks run as a PR job (above).

## Class 2 questions

None in any block.

## Pitfalls

- **Grype leaves `ignoredMatches` out when it ignores nothing**, and `--show-suppressed` changes nothing in the JSON:
  read the key with a default (block 30, spec appendix A).
- **`install.sh` hardcodes the certificate identity**; `COSIGN_BINARY` is the only seam to test a wrong one. Syft
  signs with a sigstore bundle from v1.53.0, Grype from v0.120.0; cosign must be v2.5.0 or newer (block 20).
- **Without `DOWNLOAD_TAG_INSTALL_SCRIPT=false`**, the pinned `install.sh` hands over to the tag's script from
  `get.anchore.io`, so pinning it verifies nothing (block 20).
- **Under zsh, an unquoted `$files` is not split into words**: `xargs -0` over `git grep -lz` (block 10).

## Not validated

- The release steps run only on a tag, first at v5's.
- The daily scan runs the new check on `main` after the merge. It still scans v4's `mulewatch`, whose attested VEX
  names `pkg:generic/python`, so it should report both Python claims not applied, under `vex-applied-claims-mulewatch`,
  until the v5 legs replace it.
- Block 20's `syft scan registry:` with `SYFT_REGISTRY_AUTH_*` was not run locally, nor the arm64 install
  (`validate`'s arm64 leg runs it).

## Wrap counts

For the closing block.

## Next

- The closing block: the holistic review's fixes, the backlog entry "A release publishes both images or neither"
  (spec, "Not in this lot"), this handoff corrected.
- The operator reads the stack; the lead rebases it onto the current `main`; the operator merges it.
- Then the backlog, "A copy before a migration that rewrites rows" first, with "The Grype scan back on p2pwatch at the
  v5 release", whose legs will upload under the category this lot named.
