"""The error a database's opening raises short of disk space, which the command line prints in
one line."""

from pathlib import PurePath

from p2pwatch.domain.gigabytes import (
    gigabyte_tenths_rounded_down,
    gigabyte_tenths_rounded_up,
    gigabytes_from_tenths,
)


class OutOfSpaceError(Exception):
    """Too little free space in ``directory`` for ``step``, which left the database as ``outcome``
    says; ``need_bytes`` is ``None`` when the step ran out of space rather than being refused."""

    def __init__(
        self,
        *,
        step: str,
        directory: PurePath,
        free_bytes: int,
        need_bytes: int | None,
        outcome: str,
    ) -> None:
        # The free space rounded down, the need up: freeing the difference they read is enough.
        free = gigabyte_tenths_rounded_down(free_bytes)
        if need_bytes is None:
            space = f"out of space in {directory}, {gigabytes_from_tenths(free)} free"
        else:
            need = gigabyte_tenths_rounded_up(need_bytes)
            space = (
                f"{gigabytes_from_tenths(need)} needed in {directory}, "
                f"{gigabytes_from_tenths(free)} free, {gigabytes_from_tenths(need - free)} to free"
            )
        super().__init__(f"{step}: {space}; {outcome}")
