from pathlib import Path

from vex_checks.application.ports.driven.source_rule_reader import SourceRuleReader


class FilesystemSourceRuleReader(SourceRuleReader):
    """The rules of a directory, one ``<id>.yml`` file each: a rule's id is its file's name."""

    def __init__(self, *, rules_directory: Path) -> None:
        self._rules_directory = rules_directory

    def read_source_rule_ids(self) -> set[str]:
        # iterdir, not glob: an absent directory raises instead of reading no rule.
        rule_paths = [path for path in self._rules_directory.iterdir() if path.suffix == ".yml"]
        for rule_path in rule_paths:
            # ast-grep reports the id inside the file: refuse one that is not its file's name.
            if f"id: {rule_path.stem}" not in rule_path.read_text().splitlines():
                raise ValueError(f"{rule_path.name}: its id is not {rule_path.stem}")
        return {rule_path.stem for rule_path in rule_paths}
