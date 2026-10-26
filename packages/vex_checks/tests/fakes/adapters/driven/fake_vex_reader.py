from collections.abc import Mapping
from pathlib import PurePath

from vex_checks.application.ports.driven.vex_reader import VexReader
from vex_checks.domain.broken_input_error import BrokenInputError


class FakeVexReader(VexReader):
    """Reads the claims given for a VEX file, and ``claims`` from any other; raises
    ``BrokenInputError`` naming a path given as unreadable."""

    def __init__(
        self,
        claims: dict[str, str],
        *,
        claims_by_vex_path: Mapping[PurePath, dict[str, str]] | None = None,
        unreadable_vex_paths: frozenset[PurePath] = frozenset(),
    ) -> None:
        self._claims = claims
        self._claims_by_vex_path = claims_by_vex_path or {}
        self._unreadable_vex_paths = unreadable_vex_paths

    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        if vex_path in self._unreadable_vex_paths:
            raise BrokenInputError(f"{vex_path}: no such file")
        return dict(self._claims_by_vex_path.get(vex_path, self._claims))
