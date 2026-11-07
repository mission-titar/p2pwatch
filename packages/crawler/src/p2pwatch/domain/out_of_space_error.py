"""The error a database's opening raises short of disk space, which the command line prints in
one line."""

from pathlib import PurePath

from p2pwatch.domain.gigabytes import gigabytes, gigabytes_rounded_up


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
        if need_bytes is None:
            space = f"out of space in {directory}, {gigabytes(free_bytes)} free"
        else:
            space = (
                f"{gigabytes(need_bytes)} needed in {directory}, {gigabytes(free_bytes)} free, "
                f"{gigabytes_rounded_up(need_bytes - free_bytes)} to free"
            )
        super().__init__(f"{step}: {space}; {outcome}")
