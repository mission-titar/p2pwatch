from p2pwatch.domain.gigabytes import gigabytes, gigabytes_rounded_up


def test_a_size_reads_in_gigabytes_to_one_decimal() -> None:
    assert gigabytes(7_495_532_544) == "7.5 GB"


def test_a_size_to_free_is_rounded_up_to_the_next_tenth() -> None:
    assert gigabytes_rounded_up(7_400_000_001) == "7.5 GB"
    assert gigabytes_rounded_up(7_400_000_000) == "7.4 GB"
