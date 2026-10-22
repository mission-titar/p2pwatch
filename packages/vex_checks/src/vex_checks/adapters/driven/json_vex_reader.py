import json
from pathlib import Path, PurePath

from vex_checks.application.ports.driven.vex_reader import VexReader


class OpenVexReader(VexReader):
    """An OpenVEX document as a JSON file at the path each call is given."""

    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        document = json.loads(Path(vex_path).read_text())
        return {
            statement["vulnerability"]["name"]: statement["justification"]
            for statement in document["statements"]
            if statement["status"] == "not_affected"
        }
