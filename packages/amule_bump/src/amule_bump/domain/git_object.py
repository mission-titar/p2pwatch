from dataclasses import dataclass
from enum import StrEnum

from amule_bump.domain.bump_error import BumpError


class GitObjectKind(StrEnum):
    COMMIT = "commit"
    TAG = "tag"
    TREE = "tree"
    BLOB = "blob"


@dataclass(kw_only=True, frozen=True)
class GitObject:
    """An object of a git repository, as a ref or an annotated tag names it."""

    kind: GitObjectKind
    object_id: str


def tagged_commit_id(tag: str, *, git_object: GitObject) -> str:
    """The commit's id ``tag`` names once peeled; raises ``BumpError`` when it names no commit."""
    if git_object.kind != GitObjectKind.COMMIT:
        raise BumpError(f"tag {tag} points at a {git_object.kind}, not a commit")
    return git_object.object_id
