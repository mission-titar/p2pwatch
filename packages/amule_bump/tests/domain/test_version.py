import pytest

from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.version import check_release_tag, is_newer


def test_check_release_tag_accepts_a_plain_version() -> None:
    check_release_tag("3.1.0")


@pytest.mark.parametrize("tag", ["v3.1.0", "3.1", "3.1.0-rc1", "3.1.0\n", "../3.1.0"])
def test_check_release_tag_rejects_a_tag_that_is_not_a_plain_version(tag: str) -> None:
    with pytest.raises(BumpError, match="unexpected upstream release tag"):
        check_release_tag(tag)


@pytest.mark.parametrize(
    ("candidate", "pinned", "expected"),
    [
        ("3.1.0", "3.0.1", True),
        ("3.10.0", "3.9.0", True),
        ("3.1.0", "3.1.0", False),
        ("3.0.1", "3.1.0", False),
    ],
)
def test_is_newer_compares_versions_numerically(
    *, candidate: str, pinned: str, expected: bool
) -> None:
    assert is_newer(candidate, pinned=pinned) is expected


def test_is_newer_rejects_a_pinned_value_that_is_not_a_plain_version() -> None:
    with pytest.raises(BumpError, match="not a plain X.Y.Z version: 'main'"):
        is_newer("3.1.0", pinned="main")
