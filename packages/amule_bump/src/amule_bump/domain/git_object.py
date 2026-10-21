from dataclasses import dataclass
from enum import StrEnum


class GitObjectKind(StrEnum):
    COMMIT = "commit"
    TAG = "tag"
    TREE = "tree"
    BLOB = "blob"


@dataclass(frozen=True)
class GitObject:
    """An object of a git repository, as a ref or an annotated tag names it."""

    kind: GitObjectKind
    object_id: str
