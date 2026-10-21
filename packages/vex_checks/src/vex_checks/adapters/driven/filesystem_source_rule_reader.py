from pathlib import Path

from vex_checks.ports.driven.source_rule_reader import SourceRuleReader


class FilesystemSourceRuleReader(SourceRuleReader):
    """The rules of a directory, one ``<id>.yml`` file each: a rule's id is its file's name."""

    def __init__(self, *, rules_directory: Path) -> None:
        self._rules_directory = rules_directory

    def read_source_rule_ids(self) -> set[str]:
        # iterdir, not glob: an absent directory raises instead of reading no rule.
        return {path.stem for path in self._rules_directory.iterdir() if path.suffix == ".yml"}
