"""Where a check's problems point: the VEX they concern."""

from pathlib import PurePath


def locate_vex(vex_path: PurePath, *, repository_root: PurePath) -> str:
    """Relative to the repository's root, or as given outside it (CI passes one under /tmp)."""
    return (
        str(vex_path.relative_to(repository_root))
        if vex_path.is_relative_to(repository_root)
        else str(vex_path)
    )
