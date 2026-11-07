from pathlib import PurePath

from p2pwatch.domain.broken_input_error import BrokenInputError


def test_a_broken_file_carries_its_reason_apart_and_prints_its_file_first() -> None:
    error = BrokenInputError(PurePath("/srv/c.yml"), reason="not UTF-8")
    assert error.reason == "not UTF-8"
    assert str(error) == "/srv/c.yml: not UTF-8"
