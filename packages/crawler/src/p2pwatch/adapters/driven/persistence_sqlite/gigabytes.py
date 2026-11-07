"""A size as the start's lines give it to the operator."""


def gigabytes(size_bytes: int) -> str:
    return f"{size_bytes / 1e9:.1f} GB"
