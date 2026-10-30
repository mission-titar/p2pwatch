import time
from collections.abc import Iterator
from urllib.error import HTTPError

import pytest

from amule_bump.adapters.driven.github_upstream_client import GithubUpstreamClient
from amule_bump.domain.git_object import GitObject, GitObjectKind
from tests.fakes.fake_github_server import FakeGithubServer

REPO = "/repos/amule-org/amule"
TAG_OBJECT = "6ccbfdf785390c25c8b01652684f5b06fb18e034"
COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"


@pytest.fixture
def github() -> Iterator[FakeGithubServer]:
    with FakeGithubServer() as github:
        yield github


def upstream_client(github: FakeGithubServer, *, token: str | None = None) -> GithubUpstreamClient:
    return GithubUpstreamClient(
        github.api_url,
        full_name="amule-org/amule",
        token=token,
        url_opener=github.url_opener,
        timeout_seconds=0.2,
    )


def test_latest_release_tag_is_read_from_the_api_url_with_the_token(
    github: FakeGithubServer,
) -> None:
    github.answer_json(f"{REPO}/releases/latest", document={"tag_name": "3.1.0", "draft": False})
    assert upstream_client(github, token="secret").read_latest_release_tag() == "3.1.0"
    [(_, headers)] = github.requests
    assert headers["Authorization"] == "Bearer secret"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_requests_go_anonymous_without_a_token(github: FakeGithubServer) -> None:
    github.answer_json(f"{REPO}/releases/latest", document={"tag_name": "3.1.0"})
    upstream_client(github).read_latest_release_tag()
    [(_, headers)] = github.requests
    assert "Authorization" not in headers


def test_tag_target_is_the_object_the_tag_ref_names(github: FakeGithubServer) -> None:
    github.answer_json(
        f"{REPO}/git/ref/tags/3.1.0",
        document={"ref": "refs/tags/3.1.0", "object": {"type": "tag", "sha": TAG_OBJECT}},
    )
    assert upstream_client(github).read_tag_target("3.1.0") == GitObject(
        kind=GitObjectKind.TAG, object_id=TAG_OBJECT
    )


def test_annotated_tag_target_is_the_object_the_tag_object_names(
    github: FakeGithubServer,
) -> None:
    github.answer_json(
        f"{REPO}/git/tags/{TAG_OBJECT}",
        document={"tag": "3.1.0", "object": {"type": "commit", "sha": COMMIT}},
    )
    assert upstream_client(github).read_annotated_tag_target(TAG_OBJECT) == GitObject(
        kind=GitObjectKind.COMMIT, object_id=COMMIT
    )


def test_file_is_the_raw_content_at_a_ref(github: FakeGithubServer) -> None:
    github.answer_raw(
        f"{REPO}/contents/docs/CHANGELOG.md?ref=3.1.0",
        status=200,
        body="## Version 3.1.0 é\n".encode(),
    )
    assert (
        upstream_client(github).read_file("3.1.0", path="docs/CHANGELOG.md")
        == "## Version 3.1.0 é\n"
    )


def test_file_absent_at_the_ref_reads_as_empty(github: FakeGithubServer) -> None:
    github.answer_raw(f"{REPO}/contents/docs/api/REFERENCE.md?ref=3.0.1", status=404, body=b"{}")
    assert upstream_client(github).read_file("3.0.1", path="docs/api/REFERENCE.md") == ""


def test_file_lets_any_other_http_error_through(github: FakeGithubServer) -> None:
    github.answer_raw(f"{REPO}/contents/docs/CHANGELOG.md?ref=3.1.0", status=403, body=b"{}")
    with pytest.raises(HTTPError, match="403"):
        upstream_client(github).read_file("3.1.0", path="docs/CHANGELOG.md")


def test_a_request_unanswered_within_the_timeout_fails(github: FakeGithubServer) -> None:
    github.is_holding = True
    started = time.monotonic()  # noqa: TID251
    with pytest.raises(TimeoutError, match="timed out"):
        upstream_client(github).read_latest_release_tag()
    # The 0.2 s given, not a timeout of its own.
    assert time.monotonic() - started < 5  # noqa: TID251
