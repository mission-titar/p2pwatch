from p2pwatch.domain.broken_input_error import BrokenInputError


def test_a_broken_file_carries_its_reason() -> None:
    assert BrokenInputError("not UTF-8").reason == "not UTF-8"
