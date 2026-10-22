"""The command line, wired to the real checks."""

import json
from pathlib import Path

import pytest

from vex_checks.composition.command_line import build_command_line

_REPO_ROOT = Path(__file__).parents[4]


def _run(argv: list[str], env: dict[str, str], cwd: Path) -> int:
    return build_command_line(repo_root=_REPO_ROOT, env=env, cwd=cwd).run(argv)


def _write(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document))
    return path


def test_image_claims_locates_the_problems_at_the_vex_relative_to_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    amule = {"type": "UnknownPackage", "name": "amule", "version": "2.1.1"}
    artifacts = [{**amule, "purl": "pkg:generic/amule@2.1.1"}]
    sbom = _write(tmp_path / "sbom.syft.json", {"artifacts": artifacts})
    vex = "security/amule.vex.openvex.json"

    assert _run(["image-claims", "--sbom", str(sbom), "--vex", vex], {}, _REPO_ROOT) == 1

    assert capsys.readouterr().out == (
        "::error::CVE-2006-2691: declared amule 2.1.1 is below 2.1.2"
        " (security/amule.vex.openvex.json)\n"
        "::error::CVE-2006-2692: declared amule 2.1.1 is below 2.1.2"
        " (security/amule.vex.openvex.json)\n"
    )


def test_stale_claims_runs_the_grype_found_on_the_path_of_its_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The stand-in reports nothing, so every claim of the VEX is stale.
    grype = tmp_path / "grype"
    grype.write_text("#!/bin/sh\necho '{\"matches\": []}'\n")
    grype.chmod(0o755)
    sbom = _write(tmp_path / "sbom.syft.json", {"artifacts": []})
    argv = ["stale-claims", "--sbom", str(sbom), "--vex", "security/amule.vex.openvex.json"]

    assert _run(argv, {"PATH": str(tmp_path)}, _REPO_ROOT) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines
    assert all(
        line.endswith(": no longer reported by Grype (security/amule.vex.openvex.json)")
        for line in lines
    )


def test_claim_coverage_finds_the_repository_s_claims_premises_and_source_rules_in_bijection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["claim-coverage"], {}, tmp_path) == 0

    assert capsys.readouterr().out == ""
