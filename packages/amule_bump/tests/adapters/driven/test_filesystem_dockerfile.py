from pathlib import Path

import pytest

from amule_bump.adapters.driven.filesystem_dockerfile import FilesystemDockerfile


def test_read_dockerfile_returns_the_file_s_text(tmp_path: Path) -> None:
    dockerfile_path = tmp_path / "Dockerfile"
    dockerfile_path.write_text("FROM debian\n")
    assert FilesystemDockerfile().read_dockerfile(dockerfile_path) == "FROM debian\n"


def test_read_dockerfile_of_an_absent_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FilesystemDockerfile().read_dockerfile(tmp_path / "absent")


def test_write_dockerfile_replaces_the_file_s_text(tmp_path: Path) -> None:
    dockerfile_path = tmp_path / "Dockerfile"
    dockerfile_path.write_text("FROM debian\nARG A=1\n")
    FilesystemDockerfile().write_dockerfile(dockerfile_path, "FROM debian\n")
    assert dockerfile_path.read_text() == "FROM debian\n"
