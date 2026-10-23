from pathlib import Path, PurePath

from amule_bump.adapters.driven.github_actions_bump_announcer import GithubActionsBumpAnnouncer


def test_announce_bump_appends_the_version_and_the_body_s_path(tmp_path: Path) -> None:
    output_path = tmp_path / "output"
    output_path.write_text("earlier=kept\n")
    GithubActionsBumpAnnouncer(output_path).announce_bump("3.1.0", PurePath("/tmp/body.md"))
    assert output_path.read_text() == "earlier=kept\nversion=3.1.0\nbody-path=/tmp/body.md\n"
