"""PosixAmuledDirectoryPreparer: every directory created, then each chowned, never what it holds."""

from pathlib import Path

from p2pwatch_amule.adapters.driven.posix_amuled_directory_preparer import (
    PosixAmuledDirectoryPreparer,
)
from p2pwatch_amule.domain.identifiers import Gid, Uid
from tests.fakes.adapters.driven.fake_ownership import FakeOwnership


def test_missing_directories_are_created_then_owned(tmp_path: Path) -> None:
    owned_directories = [tmp_path / "home/amule", tmp_path / "home/amule/.aMule"]
    ownership = FakeOwnership()
    preparer = PosixAmuledDirectoryPreparer(
        owned_directories=owned_directories, change_owner=ownership.change_owner
    )

    preparer.prepare_amuled_directories(Uid(1000), Gid(1001))

    assert all(directory.is_dir() for directory in owned_directories)
    assert ownership.chowns == [
        (directory, Uid(1000), Gid(1001)) for directory in owned_directories
    ]


def test_what_a_directory_holds_is_left_alone(tmp_path: Path) -> None:
    incoming = tmp_path / "downloads/incoming"
    incoming.mkdir(parents=True)
    (incoming / "episode.avi").write_text("frames")
    ownership = FakeOwnership()
    preparer = PosixAmuledDirectoryPreparer(
        owned_directories=[incoming], change_owner=ownership.change_owner
    )

    preparer.prepare_amuled_directories(Uid(1000), Gid(1001))

    assert (incoming / "episode.avi").read_text() == "frames"
    assert ownership.chowns == [(incoming, Uid(1000), Gid(1001))]
