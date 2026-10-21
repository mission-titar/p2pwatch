"""PosixMountPointPreparer: every directory created, then each chowned, never what it holds."""

from pathlib import Path

from p2pwatch_amule.adapters.driven.posix_mount_point_preparer import PosixMountPointPreparer


class FakeOwnership:
    """Records each chown it is asked for: the gate cannot chown to another uid."""

    def __init__(self) -> None:
        self.chowns: list[tuple[Path, int, int]] = []

    def change_owner(self, path: Path, uid: int, gid: int) -> None:
        self.chowns.append((path, uid, gid))


def test_missing_directories_are_created_then_owned(tmp_path: Path) -> None:
    owned_directories = [tmp_path / "home/amule", tmp_path / "home/amule/.aMule"]
    ownership = FakeOwnership()
    preparer = PosixMountPointPreparer(
        owned_directories=owned_directories, change_owner=ownership.change_owner
    )

    preparer.prepare_mount_points(1000, 1001)

    assert all(directory.is_dir() for directory in owned_directories)
    assert ownership.chowns == [(directory, 1000, 1001) for directory in owned_directories]


def test_what_a_mount_point_holds_is_left_alone(tmp_path: Path) -> None:
    incoming = tmp_path / "downloads/incoming"
    incoming.mkdir(parents=True)
    (incoming / "episode.avi").write_text("frames")
    ownership = FakeOwnership()
    preparer = PosixMountPointPreparer(
        owned_directories=[incoming], change_owner=ownership.change_owner
    )

    preparer.prepare_mount_points(1000, 1001)

    assert (incoming / "episode.avi").read_text() == "frames"
    assert ownership.chowns == [(incoming, 1000, 1001)]
