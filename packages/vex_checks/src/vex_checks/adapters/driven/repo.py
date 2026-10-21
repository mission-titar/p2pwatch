"""Repo-relative paths the checks read: the VEX files.

Everything is derived from the repo root (six parents up from this module), so
the checks stay correct no matter the working directory the gate runs from.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[6]


def repo_root() -> Path:
    return _ROOT


def vex_files() -> dict[str, Path]:
    return {
        image: _ROOT / "security" / f"{image}.vex.openvex.json" for image in ("crawler", "amule")
    }
