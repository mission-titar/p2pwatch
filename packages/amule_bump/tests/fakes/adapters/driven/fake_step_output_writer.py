from pathlib import PurePath

from amule_bump.application.ports.driven.step_output_writer import BumpAnnouncer


class FakeBumpAnnouncer(BumpAnnouncer):
    """Records each announcement, in order."""

    def __init__(self) -> None:
        self.step_outputs: list[tuple[str, PurePath]] = []

    def announce_bump(self, version: str, body_path: PurePath) -> None:
        self.step_outputs.append((version, body_path))
