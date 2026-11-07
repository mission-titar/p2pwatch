from p2pwatch.domain.gigabytes import (
    gigabyte_tenths_rounded_down,
    gigabyte_tenths_rounded_up,
    gigabytes,
    gigabytes_from_tenths,
)


def test_a_size_reads_in_gigabytes_to_one_decimal() -> None:
    assert gigabytes(7_495_532_544) == "7.5 GB"


def test_a_size_rounded_up_counts_the_next_tenth_of_a_gigabyte() -> None:
    assert gigabyte_tenths_rounded_up(7_400_000_001) == 75
    assert gigabyte_tenths_rounded_up(7_400_000_000) == 74


def test_a_size_rounded_down_counts_the_tenths_of_a_gigabyte_it_holds_whole() -> None:
    assert gigabyte_tenths_rounded_down(7_499_999_999) == 74
    assert gigabyte_tenths_rounded_down(7_500_000_000) == 75


def test_tenths_of_a_gigabyte_read_in_gigabytes_to_one_decimal() -> None:
    assert gigabytes_from_tenths(75) == "7.5 GB"
