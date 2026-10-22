from collections.abc import Mapping
from pathlib import PurePath

from vex_checks.application.ports.driven.vex_reader import VexReader


class FakeVexReader(VexReader):
    """Reads the claims given for a VEX file, and ``claims`` from any other."""

    def __init__(
        self,
        claims: dict[str, str],
        *,
        claims_by_vex_path: Mapping[PurePath, dict[str, str]] | None = None,
    ) -> None:
        self._claims = claims
        self._claims_by_vex_path = claims_by_vex_path or {}

    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        return dict(self._claims_by_vex_path.get(vex_path, self._claims))
