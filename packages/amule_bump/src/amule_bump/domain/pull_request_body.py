import difflib
import re
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass

from amule_bump.domain.dockerfile import Pin
from amule_bump.domain.upstream import UPSTREAM

PULL_REQUEST_BODY_FILENAME = "amule-bump-pr-body.md"
CHANGELOG_PATH = "docs/CHANGELOG.md"
CHANGELOG_MAX_CHARACTERS = 20_000
DIFF_MAX_CHARACTERS = 18_000
WATCHED_FILES = ("cmake/options.cmake", "docs/api/REFERENCE.md")
TRUNCATION_NOTICE = "[truncated, see the compare link above]"

CHECKLIST = """## Checklist

- [ ] Read the changelog: anything that changes the daemon's defaults or the network behaviour?
- [ ] `options.cmake` diff: a new switch to set explicitly in the Dockerfile's CMake options?
- [ ] `REFERENCE.md` diff: does the `amule_api` adapter need a change (with its tests first)?
- [ ] `p2pwatch_amule.domain.conf`: does a default we override or rely on change?
- [ ] CI green on amd64 and arm64.
- [ ] Merge, then tag a release (`vX.Y.Z - aMule {version}`): the image only changes on a tag.
"""


@dataclass(frozen=True)
class WatchedFile:
    """One of the ``WATCHED_FILES``, its text at the old pin's tag and at the new one's."""

    path: str
    old_text: str
    new_text: str


def build_pull_request_body(
    old: Pin,
    new: Pin,
    changelog: str,
    watched_files: Sequence[WatchedFile],
    changelog_width_characters: int,
) -> str:
    upstream = f"https://github.com/{UPSTREAM}"
    parts = [
        f"Bumps aMule from {old.version} to [{new.version}]({upstream}/releases/tag/{new.version})"
        f" (commit `{new.commit}`). Full upstream diff:"
        f" {upstream}/compare/{old.version}...{new.version}",
        "## Changelog",
        _changelog_part(changelog, new, changelog_width_characters),
    ]
    for watched_file in watched_files:
        parts += [
            f"## `{watched_file.path}` ({old.version} to {new.version})",
            _diff_part(old, new, watched_file),
        ]
    parts.append(CHECKLIST.format(version=new.version))
    return "\n\n".join(parts)


def changelog_section(changelog: str, version: str) -> str:
    """From the `## Version <version> ` heading down to the next `## Version ` one."""
    kept, inside = [], False
    for line in changelog.splitlines(keepends=True):
        if line.startswith("## Version "):
            inside = line.startswith(f"## Version {version} ")
        if inside:
            kept.append(line)
    return "".join(kept).strip()


def tag_diff(old: Pin, new: Pin, watched_file: WatchedFile) -> str:
    labels = (f"{old.version}/{watched_file.path}", f"{new.version}/{watched_file.path}")
    diff = difflib.unified_diff(
        watched_file.old_text.splitlines(), watched_file.new_text.splitlines(), *labels, lineterm=""
    )
    return "".join(f"{line}\n" for line in diff)


def wrap(text: str, width: int) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        lines += textwrap.wrap(line, width, break_long_words=False, break_on_hyphens=False) or [""]
    return "\n".join(lines) + "\n"


def clip(text: str, limit: int) -> str:
    """Whole lines up to `limit` characters: GitHub rejects a PR body over 65536."""
    if len(text) <= limit:
        return text
    kept = text[:limit].rpartition("\n")[0]
    return f"{kept}\n{TRUNCATION_NOTICE}\n"


def fenced(text: str, language: str) -> str:
    # Upstream "#123" and "@name" would otherwise link to our issues and ping our users.
    longest_backtick_run = max((len(run) for run in re.findall("`+", text)), default=0)
    fence = "`" * max(4, longest_backtick_run + 1)
    return f"{fence}{language}\n{text.removesuffix('\n')}\n{fence}"


def _changelog_part(changelog: str, new: Pin, changelog_width_characters: int) -> str:
    section = changelog_section(changelog, new.version)
    if not section:
        return f"No `## Version {new.version}` section in upstream's {CHANGELOG_PATH}."
    return fenced(clip(wrap(section, changelog_width_characters), CHANGELOG_MAX_CHARACTERS), "text")


def _diff_part(old: Pin, new: Pin, watched_file: WatchedFile) -> str:
    diff = tag_diff(old, new, watched_file)
    if not diff:
        return "No change between the two tags."
    return fenced(clip(diff, DIFF_MAX_CHARACTERS), "diff")
