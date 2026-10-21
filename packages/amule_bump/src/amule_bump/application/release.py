import re

from amule_bump.domain.bump_error import BumpError
from amule_bump.domain.git_object import GitObjectKind
from amule_bump.ports.driven.repo_reader import RepoReader


def latest_release_tag(repo_reader: RepoReader) -> str:
    tag = repo_reader.read_latest_release_tag()
    # The tag ends up in a URL, a branch name and the Dockerfile: accept a plain version only.
    if not _is_plain_version(tag):
        raise BumpError(f"unexpected upstream release tag {tag!r}")
    return tag


def is_newer(candidate: str, pinned: str) -> bool:
    return _version(candidate) > _version(pinned)


def peeled_commit(repo_reader: RepoReader, tag: str) -> str:
    """The commit the tag names, never the annotated tag object: BuildKit's --checksum wants it."""
    git_object = repo_reader.read_tag_target(tag)
    while git_object.kind == GitObjectKind.TAG:
        git_object = repo_reader.read_annotated_tag_target(git_object.object_id)
    if git_object.kind != GitObjectKind.COMMIT:
        raise BumpError(f"tag {tag} points at a {git_object.kind}, not a commit")
    return git_object.object_id


def _version(text: str) -> tuple[int, ...]:
    if not _is_plain_version(text):
        raise BumpError(f"not a plain X.Y.Z version: {text!r}")
    return tuple(int(part) for part in text.split("."))


def _is_plain_version(text: str) -> bool:
    return re.fullmatch(r"\d+\.\d+\.\d+", text) is not None
