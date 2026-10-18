"""``python -m vex_checks``: the command line wired to the real checks."""

import json
import os
from pathlib import Path

import pytest

from vex_checks.__main__ import main
from vex_checks.adapters.driving import check_claim_coverage, check_source_claims


def _write(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document))
    return path


def _vex_claiming(tmp_path: Path, cve: str) -> Path:
    claim = {"vulnerability": {"name": cve}, "status": "not_affected"}
    statement = {**claim, "justification": "vulnerable_code_not_present"}
    return _write(tmp_path / "vex.openvex.json", {"statements": [statement]})


def test_image_claims_runs_the_image_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    amule = {"type": "UnknownPackage", "name": "amule", "version": "2.1.1"}
    artifacts = [{**amule, "purl": "pkg:generic/amule@2.1.1"}]
    sbom = _write(tmp_path / "sbom.syft.json", {"artifacts": artifacts})
    vex = _vex_claiming(tmp_path, "CVE-2006-2691")

    assert main(["image-claims", "--sbom", str(sbom), "--vex", str(vex)]) == 1

    assert "::error::CVE-2006-2691: declared amule 2.1.1 is below 2.1.2" in capsys.readouterr().out


def test_stale_claims_runs_the_stale_check_over_grype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    grype = tmp_path / "grype"
    grype.write_text("#!/bin/sh\necho '{\"matches\": []}'\n")
    grype.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    sbom = _write(tmp_path / "sbom.syft.json", {"artifacts": []})
    vex = _vex_claiming(tmp_path, "CVE-A")

    assert main(["stale-claims", "--sbom", str(sbom), "--vex", str(vex)]) == 1

    assert "::error::CVE-A: no longer reported by Grype" in capsys.readouterr().out


def test_source_claims_runs_the_source_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "leak.py").write_text("import imaplib\n")
    monkeypatch.setattr(check_source_claims, "source_dirs", lambda: [tmp_path])

    assert main(["source-claims"]) == 1

    assert "::error::CVE-2025-15366" in capsys.readouterr().out


def test_claim_coverage_runs_the_coverage_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check_claim_coverage, "PREMISES", {})

    assert main(["claim-coverage"]) == 1

    assert "claim has no premise" in capsys.readouterr().out
