from pathlib import PurePath

from amule_bump.application.ports.driven.bump_announcer import BumpAnnouncer


class GithubActionsBumpAnnouncer(BumpAnnouncer):
    """Appends to Actions' step-outputs file, the path ``GITHUB_OUTPUT`` names."""

    def __init__(self, output_path: PurePath) -> None:
        self._output_path = output_path

    def announce_bump(self, version: str, body_path: PurePath) -> None:
        with open(self._output_path, "a") as output:
            output.write(f"version={version}\nbody-path={body_path}\n")
