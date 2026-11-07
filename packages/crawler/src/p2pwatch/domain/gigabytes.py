"""A size as the start's lines give it to the operator."""

_TENTH_OF_A_GIGABYTE = 100_000_000


def gigabytes(size_bytes: int) -> str:
    return f"{size_bytes / 1e9:.1f} GB"


def gigabyte_tenths_rounded_up(size_bytes: int) -> int:
    return -(-size_bytes // _TENTH_OF_A_GIGABYTE)


def gigabyte_tenths_rounded_down(size_bytes: int) -> int:
    return size_bytes // _TENTH_OF_A_GIGABYTE


def gigabytes_from_tenths(tenths: int) -> str:
    return f"{tenths / 10:.1f} GB"
