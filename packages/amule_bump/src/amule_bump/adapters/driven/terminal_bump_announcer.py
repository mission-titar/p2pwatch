from pathlib import PurePath

from amule_bump.application.ports.driven.bump_announcer import BumpAnnouncer


class TerminalBumpAnnouncer(BumpAnnouncer):
    """Prints the step outputs, for a bump run by hand outside Actions."""

    def announce_bump(self, version: str, body_path: PurePath) -> None:
        print(f"version={version}\nbody-path={body_path}")
