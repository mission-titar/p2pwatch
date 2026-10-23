"""The error a merge raises, which the merge and the command line both use."""

from pathlib import PurePath


class MergeError(Exception):
    """A merge refused before copying, or a copy that failed: each source is copied whole or not."""


class OutputIsSourceError(MergeError):
    """A new output that is also one of the sources, refused before any write."""

    def __init__(self, output: PurePath) -> None:
        super().__init__(str(output))
        self.output = output
