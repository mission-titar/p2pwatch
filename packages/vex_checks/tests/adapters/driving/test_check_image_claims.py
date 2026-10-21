import json
from pathlib import Path
from typing import cast

import pytest

from vex_checks.adapters.driven.json_vex_reader import JsonVexReader
from vex_checks.adapters.driven.repo import repo_root
from vex_checks.adapters.driving import check_image_claims
from vex_checks.domain import registry
from vex_checks.domain.descriptors import (
    DeclaredMinVersion,
    DpkgMinVersion,
    DpkgPackageAbsent,
    ModuleNotImported,
    Premise,
)

# Tests inject their own premises, keyed on CVEs the real crawler VEX does claim: the document
# stays a genuine fixture (and lives under the repo, taking the in-repo repo.display_path
# branch) while the premises stay under test control.
_CRAWLER_VEX = repo_root() / "security" / "crawler.vex.openvex.json"
_CRAWLER_VEX_RELPATH = "security/crawler.vex.openvex.json"
_AMULE_VEX = repo_root() / "security" / "amule.vex.openvex.json"

_CLAIMED_IMAGE_CVE = "CVE-2025-15367"
_CLAIMED_SOURCE_CVE = "CVE-2025-15366"

# Three premises, one per branch of main's filter: an image premise whose CVE is claimed (kept),
# a source premise whose CVE is claimed (scoped out), an image premise nothing claims (skipped).
_PREMISES: dict[str, Premise] = {
    _CLAIMED_IMAGE_CVE: DpkgPackageAbsent("nghttp2"),
    _CLAIMED_SOURCE_CVE: ModuleNotImported("imaplib"),
    "CVE-UNCLAIMED": DpkgMinVersion("curl", "99.0"),
    "CVE-2006-2691": DeclaredMinVersion("amule", "2.1.2"),
}


@pytest.fixture(autouse=True)
def _premises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_image_claims, "PREMISES", _PREMISES)


def _write_sbom(tmp_path: Path, artifacts: list[dict[str, str]]) -> Path:
    path = tmp_path / "sbom.syft.json"
    path.write_text(json.dumps({"artifacts": artifacts}))
    return path


def _violating_sbom(tmp_path: Path) -> Path:
    # nghttp2 present contradicts the PackageAbsent("nghttp2") premise.
    return _write_sbom(tmp_path, [{"type": "deb", "name": "nghttp2", "version": "1.64.0-1"}])


def _clean_sbom(tmp_path: Path) -> Path:
    # curl below the unclaimed premise's minimum: skipped, since nothing claims that CVE.
    return _write_sbom(
        tmp_path,
        [
            {"type": "deb", "name": "libnghttp2-14", "version": "1.64.0-1"},
            {"type": "deb", "name": "curl", "version": "8.14.1-2"},
        ],
    )


def _write_vex(tmp_path: Path, cve: str, justification: str) -> Path:
    doc = {
        "statements": [
            {
                "vulnerability": {"name": cve},
                "status": "not_affected",
                "justification": justification,
            }
        ]
    }
    path = tmp_path / "vex.openvex.json"
    path.write_text(json.dumps(doc))
    return path


def test_fail_mode_flags_a_present_package_and_prints_the_cve(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sbom = _violating_sbom(tmp_path)

    rc = check_image_claims.main(sbom, _CRAWLER_VEX, None, vex_reader=JsonVexReader())

    assert rc == 1
    out = capsys.readouterr().out
    assert f"::error::{_CLAIMED_IMAGE_CVE}" in out
    # The in-repo relative repo.display_path branch: the location renders repo-relative.
    assert f"({_CRAWLER_VEX_RELPATH})" in out


def test_fail_mode_flags_a_declared_component_below_its_minimum(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vex = _write_vex(tmp_path, "CVE-2006-2691", "vulnerable_code_not_present")
    sbom = _write_sbom(
        tmp_path,
        [
            {
                "type": "UnknownPackage",
                "name": "amule",
                "version": "2.1.1",
                "purl": "pkg:generic/amule@2.1.1",
            }
        ],
    )

    rc = check_image_claims.main(sbom, vex, None, vex_reader=JsonVexReader())

    assert rc == 1
    assert "::error::CVE-2006-2691: declared amule 2.1.1 is below 2.1.2" in capsys.readouterr().out


def test_the_real_amule_claims_fail_on_an_amule_older_than_the_fix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(check_image_claims, "PREMISES", registry.PREMISES)
    sbom = _write_sbom(
        tmp_path,
        [
            {
                "type": "UnknownPackage",
                "name": "amule",
                "version": "2.1.1",
                "purl": "pkg:generic/amule@2.1.1",
            }
        ],
    )

    rc = check_image_claims.main(sbom, _AMULE_VEX, None, vex_reader=JsonVexReader())

    assert rc == 1
    out = capsys.readouterr().out
    assert "::error::CVE-2006-2691: declared amule 2.1.1 is below 2.1.2" in out
    assert "::error::CVE-2006-2692: declared amule 2.1.1 is below 2.1.2" in out


def test_fail_mode_returns_zero_on_a_clean_sbom(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sbom = _clean_sbom(tmp_path)

    rc = check_image_claims.main(sbom, _CRAWLER_VEX, None, vex_reader=JsonVexReader())

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_a_vex_with_no_image_claim_lets_any_sbom_pass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Scoping: a document claiming only a source-family CVE filters every image premise
    # out, so even a package-laden SBOM yields no violation.
    vex = _write_vex(tmp_path, _CLAIMED_SOURCE_CVE, "vulnerable_code_not_in_execute_path")
    sbom = _violating_sbom(tmp_path)

    rc = check_image_claims.main(sbom, vex, None, vex_reader=JsonVexReader())

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_fail_mode_renders_an_out_of_repo_vex_path_verbatim(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The repo.display_path ValueError fallback: a VEX outside the repo (CI /tmp) must
    # not crash; its raw path is echoed as-is in the violation location.
    vex = _write_vex(tmp_path, _CLAIMED_IMAGE_CVE, "vulnerable_code_not_present")
    sbom = _violating_sbom(tmp_path)

    rc = check_image_claims.main(sbom, vex, None, vex_reader=JsonVexReader())

    assert rc == 1
    out = capsys.readouterr().out
    assert f"::error::{_CLAIMED_IMAGE_CVE}" in out
    assert f"({vex})" in out


def test_sarif_mode_with_violation_writes_matching_results(tmp_path: Path) -> None:
    sbom = _violating_sbom(tmp_path)
    output = tmp_path / "out.sarif"

    rc = check_image_claims.main(sbom, _CRAWLER_VEX, output, vex_reader=JsonVexReader())

    assert rc == 0
    doc = json.loads(output.read_text())
    runs = cast(list[dict[str, object]], doc["runs"])
    results = cast(list[dict[str, object]], runs[0]["results"])
    assert len(results) == 1
    result = results[0]

    assert result["ruleId"] == "unsatisfied-image-claim"
    assert result["level"] == "error"

    message = cast(dict[str, object], result["message"])
    assert _CLAIMED_IMAGE_CVE in cast(str, message["text"])

    locations = cast(list[dict[str, object]], result["locations"])
    physical = cast(dict[str, object], locations[0]["physicalLocation"])
    artifact = cast(dict[str, object], physical["artifactLocation"])
    assert artifact["uri"] == _CRAWLER_VEX_RELPATH


def test_sarif_mode_on_a_clean_sbom_writes_empty_results(tmp_path: Path) -> None:
    sbom = _clean_sbom(tmp_path)
    output = tmp_path / "out.sarif"

    rc = check_image_claims.main(sbom, _CRAWLER_VEX, output, vex_reader=JsonVexReader())

    assert rc == 0
    doc = json.loads(output.read_text())
    runs = cast(list[dict[str, object]], doc["runs"])
    assert runs[0]["results"] == []
