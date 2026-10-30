from pathlib import PurePath

from amule_bump.application.ports.driving.amule_bumper import (
    AmuleBump,
    AmuleBumper,
    PinAheadOfLatest,
    PinIsLatest,
)


class FakeAmuleBumper(AmuleBumper):
    """Records each call's options, answers with a set outcome or raises a set error."""

    def __init__(self, outcome: AmuleBump | PinIsLatest | PinAheadOfLatest | Exception) -> None:
        self._outcome = outcome
        self.calls: list[tuple[PurePath, PurePath, bool]] = []

    def bump_amule(
        self, dockerfile_path: PurePath, *, body_path: PurePath, dry_run: bool
    ) -> AmuleBump | PinIsLatest | PinAheadOfLatest:
        self.calls.append((dockerfile_path, body_path, dry_run))
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome
