import os
from pathlib import Path

import pytest

from vex_checks.adapters.driven.grype import GrypeRunner, SubprocessGrypeRunner, parse_grype_json


def test_parse_grype_json_collects_unique_ids() -> None:
    text = (
        '{"matches": ['
        '{"vulnerability": {"id": "CVE-1"}},'
        '{"vulnerability": {"id": "CVE-1"}},'
        '{"vulnerability": {"id": "GHSA-x"}}]}'
    )
    assert parse_grype_json(text) == {"CVE-1", "GHSA-x"}


def test_subprocess_runner_reports_the_ids_grype_prints_for_the_sbom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grype = tmp_path / "grype"
    grype.write_text(
        """#!/bin/sh\nprintf '{"matches": [{"vulnerability": {"id": "%s"}}]}' "$*"\n"""
    )
    grype.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    assert SubprocessGrypeRunner().run(Path("/x/sbom.json")) == {"sbom:/x/sbom.json -o json"}


class _Fake:
    def run(self, sbom_path: Path) -> set[str]:
        return {"CVE-1"}


def test_fake_satisfies_protocol() -> None:
    runner: GrypeRunner = _Fake()
    assert runner.run(Path("x")) == {"CVE-1"}
