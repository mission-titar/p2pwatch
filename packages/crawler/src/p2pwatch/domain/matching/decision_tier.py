"""``DecisionTier``: a decision's strength, from the weakest to the strongest."""

from enum import StrEnum


class DecisionTier(StrEnum):
    """A rule's tier, its value the string of ``matcher.yml``, the rows and the metrics."""

    CATALOG = "catalog"
    NOTIFY = "notify"
    DOWNLOAD = "download"

    @property
    def rank(self) -> int:
        """Higher is stronger: download, then notify, then catalog."""
        return _WEAKEST_FIRST.index(self)

    @property
    def identifies_target(self) -> bool:
        """False for ``catalog``, the catch-all tier, which keeps a file but names no episode."""
        return self is not DecisionTier.CATALOG


_WEAKEST_FIRST = (DecisionTier.CATALOG, DecisionTier.NOTIFY, DecisionTier.DOWNLOAD)
