"""The error a merge raises, which the merge and the command line both use."""


class MergeError(Exception):
    """A merge refused before copying, or a copy that failed: each source is copied whole or not."""
