from pathlib import PurePath

from vex_checks.ports.driven.vex_reader import VexReader


class FakeVexReader(VexReader):
    """Reads the same claims from any VEX file."""

    def __init__(self, claims: dict[str, str]) -> None:
        self._claims = claims

    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        return dict(self._claims)
