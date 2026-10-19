"""``python -m amule_bump``: the command line wired to the real bump and GitHub's reader."""

from pathlib import Path

import pytest

import amule_bump.__main__
from amule_bump.__main__ import main
from tests.fakes import FakeRepoReader

NEW_COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"


def test_bump_reads_upstream_with_gh_token_and_announces_to_github_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(f"ARG AMULE_VERSION=3.0.1\nARG AMULE_COMMIT={'0' * 40}\n")
    body_file = tmp_path / "body.md"
    output = tmp_path / "output"
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    opened: list[tuple[str, str | None]] = []

    def fake_repo_reader(full_name: str, token: str | None) -> FakeRepoReader:
        opened.append((full_name, token))
        return FakeRepoReader(
            json={
                "releases/latest": {"tag_name": "3.1.0"},
                "git/ref/tags/3.1.0": {"object": {"type": "commit", "sha": NEW_COMMIT}},
            }
        )

    monkeypatch.setattr(amule_bump.__main__, "GitHubRepoReader", fake_repo_reader)

    argv = ["bump", "--dockerfile", str(dockerfile), "--body-file", str(body_file)]
    assert main(argv) == 0

    assert opened == [("amule-org/amule", "secret")]
    assert f"ARG AMULE_COMMIT={NEW_COMMIT}" in dockerfile.read_text()
    assert output.read_text() == f"version=3.1.0\nbody-path={body_file}\n"
