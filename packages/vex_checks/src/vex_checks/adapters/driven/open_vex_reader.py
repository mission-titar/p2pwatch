import json
from pathlib import Path, PurePath

from vex_checks.application.ports.driven.vex_reader import VexReader
from vex_checks.domain.broken_input_error import BrokenInputError


class OpenVexReader(VexReader):
    """An OpenVEX document as a JSON file at the path each call is given."""

    def read_claims(self, vex_path: PurePath) -> dict[str, str]:
        try:
            document = json.loads(Path(vex_path).read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise BrokenInputError(f"{vex_path}: no such file") from error
        except OSError as error:
            raise BrokenInputError(f"{vex_path}: {error.strerror}") from error
        except UnicodeDecodeError as error:
            raise BrokenInputError(f"{vex_path}: not UTF-8") from error
        except json.JSONDecodeError as error:
            raise BrokenInputError(f"{vex_path}: not JSON") from error
        try:
            return {
                statement["vulnerability"]["name"]: statement["justification"]
                for statement in document["statements"]
                if statement["status"] == "not_affected"
            }
        except (KeyError, TypeError) as error:
            raise BrokenInputError(f"{vex_path}: not an OpenVEX document") from error
