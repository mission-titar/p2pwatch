"""The error a catalog copy raises, which the copier and the merge both use."""


class CatalogCopyError(Exception):
    """A catalog that cannot be opened or copied: the source being copied leaves no row."""
