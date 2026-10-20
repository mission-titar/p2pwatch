"""``python -m amule_bump``: the command line wired to the real bump and GitHub's reader."""

from pathlib import Path

import pytest

import amule_bump.__main__
from amule_bump.__main__ import main
from tests.fakes import FakeRepoReader

NEW_COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"


class OpenedRepoReaders:
    """Stands in for ``GitHubRepoReader``: records what each reader is opened on."""

    def __init__(self) -> None:
        self.opened: list[tuple[str, str | None]] = []

    def __call__(self, full_name: str, token: str | None) -> FakeRepoReader:
        self.opened.append((full_name, token))
        return FakeRepoReader(
            json={
                "releases/latest": {"tag_name": "3.1.0"},
                "git/ref/tags/3.1.0": {"object": {"type": "commit", "sha": NEW_COMMIT}},
            }
        )


@pytest.fixture
def repo_readers(monkeypatch: pytest.MonkeyPatch) -> OpenedRepoReaders:
    repo_readers = OpenedRepoReaders()
    monkeypatch.setattr(amule_bump.__main__, "GitHubRepoReader", repo_readers)
    return repo_readers


def write_dockerfile(cwd: Path) -> Path:
    dockerfile = cwd / "packages/amule/Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text(f"ARG AMULE_VERSION=3.0.1\nARG AMULE_COMMIT={'0' * 40}\n")
    return dockerfile


def test_bump_reads_upstream_with_gh_token_and_announces_to_github_output(
    tmp_path: Path, repo_readers: OpenedRepoReaders
) -> None:
    cwd, temporary_directory = tmp_path / "repo", tmp_path / "tmp"
    temporary_directory.mkdir()
    dockerfile = write_dockerfile(cwd)
    output = tmp_path / "output"
    env = {"GH_TOKEN": "secret", "GITHUB_OUTPUT": str(output)}

    assert main(["bump"], env, cwd, temporary_directory) == 0

    assert repo_readers.opened == [("amule-org/amule", "secret")]
    assert f"ARG AMULE_COMMIT={NEW_COMMIT}" in dockerfile.read_text()
    body_file = temporary_directory / "amule-bump-pr-body.md"
    assert body_file.read_text().startswith("Bumps aMule from 3.0.1 to [3.1.0]")
    assert output.read_text() == f"version=3.1.0\nbody-path={body_file}\n"


def test_bump_outside_actions_prints_its_step_outputs(
    tmp_path: Path, repo_readers: OpenedRepoReaders, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dockerfile(tmp_path)

    assert main(["bump", "--body-file", "body.md"], {}, tmp_path, tmp_path) == 0

    assert repo_readers.opened == [("amule-org/amule", None)]
    assert capsys.readouterr().out == f"version=3.1.0\nbody-path={tmp_path / 'body.md'}\n"
