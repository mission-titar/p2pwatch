from collections.abc import Iterator
from urllib.error import HTTPError

import pytest

from amule_bump.adapters.driven.github_repo_reader import GitHubRepoReader
from amule_bump.domain.git_object import GitObject, GitObjectKind
from tests.fakes import FakeGitHubServer

REPO = "/repos/amule-org/amule"
TAG_OBJECT = "6ccbfdf785390c25c8b01652684f5b06fb18e034"
COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"


@pytest.fixture
def github() -> Iterator[FakeGitHubServer]:
    with FakeGitHubServer() as github:
        yield github


def repo_reader(github: FakeGitHubServer, token: str | None = None) -> GitHubRepoReader:
    return GitHubRepoReader(github.api_url, "amule-org/amule", token, github.url_opener)


def test_latest_release_tag_is_read_from_the_api_url_with_the_token(
    github: FakeGitHubServer,
) -> None:
    github.answer_json(f"{REPO}/releases/latest", {"tag_name": "3.1.0", "draft": False})
    assert repo_reader(github, "secret").read_latest_release_tag() == "3.1.0"
    [(_, headers)] = github.requests
    assert headers["Authorization"] == "Bearer secret"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_requests_go_anonymous_without_a_token(github: FakeGitHubServer) -> None:
    github.answer_json(f"{REPO}/releases/latest", {"tag_name": "3.1.0"})
    repo_reader(github).read_latest_release_tag()
    [(_, headers)] = github.requests
    assert "Authorization" not in headers


def test_tag_target_is_the_object_the_tag_ref_names(github: FakeGitHubServer) -> None:
    github.answer_json(
        f"{REPO}/git/ref/tags/3.1.0",
        {"ref": "refs/tags/3.1.0", "object": {"type": "tag", "sha": TAG_OBJECT}},
    )
    assert repo_reader(github).read_tag_target("3.1.0") == GitObject(GitObjectKind.TAG, TAG_OBJECT)


def test_annotated_tag_target_is_the_object_the_tag_object_names(
    github: FakeGitHubServer,
) -> None:
    github.answer_json(
        f"{REPO}/git/tags/{TAG_OBJECT}",
        {"tag": "3.1.0", "object": {"type": "commit", "sha": COMMIT}},
    )
    assert repo_reader(github).read_annotated_tag_target(TAG_OBJECT) == GitObject(
        GitObjectKind.COMMIT, COMMIT
    )


def test_file_is_the_raw_content_at_a_ref(github: FakeGitHubServer) -> None:
    github.answer_raw(
        f"{REPO}/contents/docs/CHANGELOG.md?ref=3.1.0", 200, "## Version 3.1.0 é\n".encode()
    )
    assert repo_reader(github).read_file("3.1.0", "docs/CHANGELOG.md") == "## Version 3.1.0 é\n"


def test_file_absent_at_the_ref_reads_as_empty(github: FakeGitHubServer) -> None:
    github.answer_raw(f"{REPO}/contents/docs/api/REFERENCE.md?ref=3.0.1", 404, b"{}")
    assert repo_reader(github).read_file("3.0.1", "docs/api/REFERENCE.md") == ""


def test_file_lets_any_other_http_error_through(github: FakeGitHubServer) -> None:
    github.answer_raw(f"{REPO}/contents/docs/CHANGELOG.md?ref=3.1.0", 403, b"{}")
    with pytest.raises(HTTPError, match="403"):
        repo_reader(github).read_file("3.1.0", "docs/CHANGELOG.md")
