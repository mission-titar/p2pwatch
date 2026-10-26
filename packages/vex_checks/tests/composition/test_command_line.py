"""The command line, wired to the real checks."""

import json
from pathlib import Path

import pytest

from vex_checks.composition.command_line import build_command_line

_REPOSITORY_ROOT = Path(__file__).parents[4]


def _run(argv: list[str], env: dict[str, str], cwd: Path) -> int:
    return build_command_line(env=env, cwd=cwd).run(argv)


def _write(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document))
    return path


def test_image_claims_locates_the_problems_at_the_vex_relative_to_the_cwd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    amule = {"type": "UnknownPackage", "name": "amule", "version": "2.1.1"}
    artifacts = [{**amule, "purl": "pkg:generic/amule@2.1.1"}]
    sbom = _write(tmp_path / "sbom.syft.json", {"artifacts": artifacts})
    vex = "security/amule.vex.openvex.json"

    assert _run(["image-claims", "--sbom", str(sbom), "--vex", vex], {}, _REPOSITORY_ROOT) == 1

    assert capsys.readouterr().out == (
        "::error::CVE-2006-2691: declared amule 2.1.1 is below 2.1.2"
        " (security/amule.vex.openvex.json)\n"
        "::error::CVE-2006-2692: declared amule 2.1.1 is below 2.1.2"
        " (security/amule.vex.openvex.json)\n"
    )


def test_applied_claims_runs_the_grype_found_on_the_path_of_its_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The stand-in reports nothing, so every claim of the VEX is stale.
    grype = tmp_path / "grype"
    grype.write_text("#!/bin/sh\necho '{\"matches\": []}'\n")
    grype.chmod(0o755)
    sbom = _write(tmp_path / "sbom.syft.json", {"artifacts": []})
    argv = ["applied-claims", "--sbom", str(sbom), "--vex", "security/amule.vex.openvex.json"]

    assert _run(argv, {"PATH": str(tmp_path)}, _REPOSITORY_ROOT) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines
    assert all(
        line.endswith(": stale: Grype does not report it (security/amule.vex.openvex.json)")
        for line in lines
    )


def test_image_claims_locates_a_vex_outside_the_cwd_at_its_path_as_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    amule = {"type": "UnknownPackage", "name": "amule", "version": "2.1.1"}
    artifacts = [{**amule, "purl": "pkg:generic/amule@2.1.1"}]
    sbom = _write(tmp_path / "sbom.syft.json", {"artifacts": artifacts})
    vex = _REPOSITORY_ROOT / "security" / "amule.vex.openvex.json"
    argv = ["image-claims", "--sbom", str(sbom), "--vex", str(vex)]

    assert _run(argv, {}, tmp_path) == 1

    assert capsys.readouterr().out.splitlines()[0].endswith(f"is below 2.1.2 ({vex})")


def test_claim_coverage_reads_the_claims_premises_and_source_rules_under_the_cwd(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(["claim-coverage"], {}, _REPOSITORY_ROOT) == 0

    assert capsys.readouterr().out == ""
