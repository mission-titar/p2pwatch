from pathlib import PurePath

from p2pwatch.domain.merge_error import MergeError, OutputIsSourceError


def test_an_output_that_is_a_source_is_a_merge_error_carrying_its_path() -> None:
    error = OutputIsSourceError(PurePath("/data/a.db"))
    assert isinstance(error, MergeError)
    assert error.output == PurePath("/data/a.db")
