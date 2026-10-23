from pathlib import Path

from vex_checks.application.ports.driven.source_rule_reader import SourceRuleReader
from vex_checks.domain.broken_input_error import BrokenInputError


class FilesystemSourceRuleReader(SourceRuleReader):
    """The rules of a directory, one ``<id>.yml`` file each: a rule's id is its file's name."""

    def __init__(self, *, rules_directory: Path) -> None:
        self._rules_directory = rules_directory

    def read_source_rule_ids(self) -> set[str]:
        # iterdir, not glob: an absent directory raises instead of reading no rule.
        try:
            rule_paths = [path for path in self._rules_directory.iterdir() if path.suffix == ".yml"]
        except FileNotFoundError as error:
            raise BrokenInputError(f"{self._rules_directory}: no such directory") from error
        except OSError as error:
            raise BrokenInputError(f"{self._rules_directory}: {error.strerror}") from error
        for rule_path in rule_paths:
            # ast-grep reports the id inside the file: refuse one that is not its file's name.
            if f"id: {rule_path.stem}" not in _read_rule(rule_path).splitlines():
                raise BrokenInputError(f"{rule_path}: its id is not {rule_path.stem}")
        return {rule_path.stem for rule_path in rule_paths}


def _read_rule(rule_path: Path) -> str:
    try:
        return rule_path.read_text(encoding="utf-8")
    except OSError as error:
        raise BrokenInputError(f"{rule_path}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise BrokenInputError(f"{rule_path}: not UTF-8") from error
