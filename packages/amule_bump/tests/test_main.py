"""``python -m amule_bump``: the command line wired to the real bump and GitHub's reader."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from amule_bump.__main__ import main
from tests.fakes import FakeGitHubServer

NEW_COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"


@pytest.fixture
def github() -> Iterator[FakeGitHubServer]:
    """amule-org/amule released 3.1.0, a lightweight tag on ``NEW_COMMIT``."""
    with FakeGitHubServer() as github:
        github.answer_json("/repos/amule-org/amule/releases/latest", {"tag_name": "3.1.0"})
        github.answer_json(
            "/repos/amule-org/amule/git/ref/tags/3.1.0",
            {"object": {"type": "commit", "sha": NEW_COMMIT}},
        )
        yield github


def write_dockerfile(cwd: Path) -> Path:
    dockerfile = cwd / "packages/amule/Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text(f"ARG AMULE_VERSION=3.0.1\nARG AMULE_COMMIT={'0' * 40}\n")
    return dockerfile


def test_bump_reads_upstream_with_gh_token_and_announces_to_github_output(
    tmp_path: Path, github: FakeGitHubServer
) -> None:
    cwd, temporary_directory = tmp_path / "repo", tmp_path / "tmp"
    temporary_directory.mkdir()
    dockerfile = write_dockerfile(cwd)
    output = tmp_path / "output"
    env = {"GH_TOKEN": "secret", "GITHUB_OUTPUT": str(output)}

    assert main(["bump"], env, cwd, temporary_directory, github.api_url) == 0

    assert {headers["Authorization"] for _, headers in github.requests} == {"Bearer secret"}
    assert f"ARG AMULE_COMMIT={NEW_COMMIT}" in dockerfile.read_text()
    body_file = temporary_directory / "amule-bump-pr-body.md"
    assert body_file.read_text().startswith("Bumps aMule from 3.0.1 to [3.1.0]")
    assert output.read_text() == f"version=3.1.0\nbody-path={body_file}\n"


def test_bump_outside_actions_prints_its_step_outputs(
    tmp_path: Path, github: FakeGitHubServer, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dockerfile(tmp_path)

    assert main(["bump", "--body-file", "body.md"], {}, tmp_path, tmp_path, github.api_url) == 0

    assert all("Authorization" not in headers for _, headers in github.requests)
    assert capsys.readouterr().out == f"version=3.1.0\nbody-path={tmp_path / 'body.md'}\n"
