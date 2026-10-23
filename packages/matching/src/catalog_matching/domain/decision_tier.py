"""``DecisionTier``: a decision's strength, from the weakest to the strongest."""

from enum import StrEnum


class DecisionTier(StrEnum):
    """A rule's tier, its value the string of ``matcher.yml``, the rows and the metrics."""

    CATALOG = "catalog"
    NOTIFY = "notify"
    DOWNLOAD = "download"

    @property
    def rank(self) -> int:
        """Higher is stronger: the members are declared from the weakest."""
        return list(DecisionTier).index(self)
