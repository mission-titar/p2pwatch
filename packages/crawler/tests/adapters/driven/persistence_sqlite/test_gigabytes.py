from p2pwatch.adapters.driven.persistence_sqlite.gigabytes import gigabytes


def test_a_size_reads_in_gigabytes_to_one_decimal() -> None:
    assert gigabytes(7_495_532_544) == "7.5 GB"
