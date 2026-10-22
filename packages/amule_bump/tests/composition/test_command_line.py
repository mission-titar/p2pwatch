"""The command line and the bump, wired to the real adapters."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from amule_bump.composition.command_line import build_amule_bumper, build_command_line
from tests.fakes.fake_github_server import FakeGithubServer

NEW_COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"


@pytest.fixture
def github() -> Iterator[FakeGithubServer]:
    """amule-org/amule released 3.1.0, a lightweight tag on ``NEW_COMMIT``."""
    with FakeGithubServer() as github:
        github.answer_json("/repos/amule-org/amule/releases/latest", {"tag_name": "3.1.0"})
        github.answer_json(
            "/repos/amule-org/amule/git/ref/tags/3.1.0",
            {"object": {"type": "commit", "sha": NEW_COMMIT}},
        )
        yield github


def write_dockerfile(directory: Path) -> Path:
    dockerfile = directory / "Dockerfile"
    dockerfile.write_text(f"ARG AMULE_VERSION=3.0.1\nARG AMULE_COMMIT={'0' * 40}\n")
    return dockerfile


def test_bump_reads_upstream_with_gh_token_and_announces_to_github_output(
    tmp_path: Path, github: FakeGithubServer
) -> None:
    dockerfile = write_dockerfile(tmp_path)
    output = tmp_path / "output"
    env = {"GH_TOKEN": "secret", "GITHUB_OUTPUT": str(output)}
    amule_bumper = build_amule_bumper(
        env=env, github_api_url=github.api_url, url_opener=github.url_opener
    )

    amule_bumper.bump_amule(dockerfile, tmp_path / "body.md", dry_run=False)

    assert {headers["Authorization"] for _, headers in github.requests} == {"Bearer secret"}
    assert f"ARG AMULE_COMMIT={NEW_COMMIT}" in dockerfile.read_text()
    assert (tmp_path / "body.md").read_text().startswith("Bumps aMule from 3.0.1 to [3.1.0]")
    assert output.read_text() == f"version=3.1.0\nbody-path={tmp_path / 'body.md'}\n"


def test_bump_outside_actions_prints_its_step_outputs(
    tmp_path: Path, github: FakeGithubServer, capsys: pytest.CaptureFixture[str]
) -> None:
    dockerfile = write_dockerfile(tmp_path)
    amule_bumper = build_amule_bumper(
        env={}, github_api_url=github.api_url, url_opener=github.url_opener
    )

    amule_bumper.bump_amule(dockerfile, tmp_path / "body.md", dry_run=False)

    assert all("Authorization" not in headers for _, headers in github.requests)
    assert capsys.readouterr().out == f"version=3.1.0\nbody-path={tmp_path / 'body.md'}\n"


def test_bump_reads_the_dockerfile_under_cwd_before_upstream(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    command_line = build_command_line(env={}, cwd=tmp_path, temporary_directory=tmp_path)

    # Refused on the missing Dockerfile, before GitHub is asked anything.
    assert command_line.run(["bump"]) == 1

    dockerfile = tmp_path / "packages" / "amule" / "Dockerfile"
    assert capsys.readouterr().err == (
        f"error: [Errno 2] No such file or directory: '{dockerfile}'\n"
    )
