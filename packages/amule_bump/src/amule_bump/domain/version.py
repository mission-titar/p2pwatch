import re

from amule_bump.domain.bump_error import BumpError


def check_release_tag(tag: str) -> None:
    # The tag ends up in a URL, a branch name and the Dockerfile: accept a plain version only.
    if not _is_plain_version(tag):
        raise BumpError(f"unexpected upstream release tag {tag!r}")


def is_newer(candidate: str, pinned: str) -> bool:
    return _version(candidate) > _version(pinned)


def _version(text: str) -> tuple[int, ...]:
    if not _is_plain_version(text):
        raise BumpError(f"not a plain X.Y.Z version: {text!r}")
    return tuple(int(part) for part in text.split("."))


def _is_plain_version(text: str) -> bool:
    return re.fullmatch(r"\d+\.\d+\.\d+", text) is not None
