from pathlib import Path

from amule_bump.adapters.driven.filesystem_pull_request_body_writer import (
    FilesystemPullRequestDrafter,
)


def test_write_pull_request_body_replaces_the_file_s_text(tmp_path: Path) -> None:
    body_path = tmp_path / "body.md"
    body_path.write_text("an earlier body, longer than the new one\n")
    FilesystemPullRequestDrafter().draft_pull_request_body(body_path, "Bumps aMule\n")
    assert body_path.read_text() == "Bumps aMule\n"
