"""A size as the start's lines give it to the operator."""

import math


def gigabytes(size_bytes: int) -> str:
    return f"{size_bytes / 1e9:.1f} GB"


def gigabytes_rounded_up(size_bytes: int) -> str:
    """A size to free: freeing the figure it reads must be enough."""
    return f"{math.ceil(size_bytes / 1e8) / 10:.1f} GB"
