"""The error a catalog copy raises, which the copier and the merge both use."""

from p2pwatch.domain.expected_error import ExpectedError


class CatalogCopyError(ExpectedError):
    """A catalog that cannot be opened or copied: the source being copied leaves no row."""


class PartialCopyError(CatalogCopyError):
    """A copy that failed on a source, the sources copied before it staying in the destination."""
