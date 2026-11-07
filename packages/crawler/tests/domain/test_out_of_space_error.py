from pathlib import PurePath

from p2pwatch.domain.out_of_space_error import OutOfSpaceError


def test_a_known_need_reads_in_gigabytes_with_the_space_to_free() -> None:
    error = OutOfSpaceError(
        step="pre-migration copy of /data/catalog.db",
        directory=PurePath("/data"),
        free_bytes=9_200_000_000,
        need_bytes=15_300_000_000,
        outcome="nothing written",
    )
    assert str(error) == (
        "pre-migration copy of /data/catalog.db: 15.3 GB needed in /data, 9.2 GB free, "
        "6.1 GB to free; nothing written"
    )


def test_the_space_to_free_is_rounded_up() -> None:
    error = OutOfSpaceError(
        step="pre-migration copy of /data/catalog.db",
        directory=PurePath("/data"),
        free_bytes=9_200_000_000,
        need_bytes=9_200_000_001,
        outcome="nothing written",
    )
    assert "0.1 GB to free" in str(error)


def test_the_three_figures_agree_as_the_operator_reads_them() -> None:
    """The need rounded up, the free space down: freeing the difference they read is enough."""
    error = OutOfSpaceError(
        step="pre-migration copy of /data/catalog.db",
        directory=PurePath("/data"),
        free_bytes=151_000_000,
        need_bytes=840_000_000,
        outcome="nothing written",
    )
    assert "0.9 GB needed in /data, 0.1 GB free, 0.8 GB to free;" in str(error)


def test_an_unknown_need_reads_the_free_space_rounded_down() -> None:
    error = OutOfSpaceError(
        step="reclaim of /data/catalog.db",
        directory=PurePath("/data"),
        free_bytes=199_999_999,
        need_bytes=None,
        outcome="the database at version 15, its free pages not given back",
    )
    assert "out of space in /data, 0.1 GB free;" in str(error)


def test_an_unknown_need_reads_the_free_space_alone() -> None:
    error = OutOfSpaceError(
        step="migrations of /data/catalog.db (migration 7)",
        directory=PurePath("/data"),
        free_bytes=100_000_000,
        need_bytes=None,
        outcome="the database left at version 5",
    )
    assert str(error) == (
        "migrations of /data/catalog.db (migration 7): out of space in /data, 0.1 GB free; "
        "the database left at version 5"
    )
