from abc import ABC, abstractmethod


class SourceRuleReader(ABC):
    """Reads the ast-grep source rules, each backing the source claim of its advisory."""

    @abstractmethod
    def read_source_rule_ids(self) -> set[str]:
        """Each rule's id, the advisory id of the claim it backs."""
