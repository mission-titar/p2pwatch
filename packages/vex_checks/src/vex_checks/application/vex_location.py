"""Where a check's problems point: the VEX they concern."""

from pathlib import PurePath


def vex_location(vex_path: PurePath, repo_root: PurePath) -> str:
    """Relative to the repository's root, or as given outside it (CI passes one under /tmp)."""
    return (
        str(vex_path.relative_to(repo_root))
        if vex_path.is_relative_to(repo_root)
        else str(vex_path)
    )
