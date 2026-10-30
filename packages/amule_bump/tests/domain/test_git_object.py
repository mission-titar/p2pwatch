import pytest

from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.git_object import GitObject, GitObjectKind, tagged_commit_id

COMMIT = "909d304d993ee07df6c6f6acf501a6d791d53666"


def test_tagged_commit_id_is_the_commit_s_id() -> None:
    assert (
        tagged_commit_id("3.1.0", git_object=GitObject(kind=GitObjectKind.COMMIT, object_id=COMMIT))
        == COMMIT
    )


def test_tagged_commit_id_fails_on_a_tag_that_does_not_name_a_commit() -> None:
    with pytest.raises(BumpError, match="tag 3.1.0 points at a tree, not a commit"):
        tagged_commit_id("3.1.0", git_object=GitObject(kind=GitObjectKind.TREE, object_id=COMMIT))
