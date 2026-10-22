from vex_checks.application.ports.driven.source_rule_reader import SourceRuleReader


class FakeSourceRuleReader(SourceRuleReader):
    """Reads the source rules' ids it is given."""

    def __init__(self, source_rule_ids: set[str]) -> None:
        self._source_rule_ids = source_rule_ids

    def read_source_rule_ids(self) -> set[str]:
        return set(self._source_rule_ids)
