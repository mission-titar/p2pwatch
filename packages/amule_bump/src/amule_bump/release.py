import re

from amule_bump.domain.bump_error import BumpError
from amule_bump.ports.driven.repo_reader import RepoReader


def latest_release_tag(repo_reader: RepoReader) -> str:
    tag = str(repo_reader.json("releases/latest")["tag_name"])
    # The tag ends up in a URL, a branch name and the Dockerfile: accept a plain version only.
    if not _is_plain_version(tag):
        raise BumpError(f"unexpected upstream release tag {tag!r}")
    return tag


def is_newer(candidate: str, pinned: str) -> bool:
    return _version(candidate) > _version(pinned)


def peeled_commit(repo_reader: RepoReader, tag: str) -> str:
    """The commit the tag names, never the annotated tag object: BuildKit's --checksum wants it."""
    git_object = repo_reader.json(f"git/ref/tags/{tag}")["object"]
    while git_object["type"] == "tag":
        git_object = repo_reader.json(f"git/tags/{git_object['sha']}")["object"]
    if git_object["type"] != "commit":
        raise BumpError(f"tag {tag} points at a {git_object['type']}, not a commit")
    return str(git_object["sha"])


def _version(text: str) -> tuple[int, ...]:
    if not _is_plain_version(text):
        raise BumpError(f"not a plain X.Y.Z version: {text!r}")
    return tuple(int(part) for part in text.split("."))


def _is_plain_version(text: str) -> bool:
    return re.fullmatch(r"\d+\.\d+\.\d+", text) is not None
