"""Tests for the lines inside a function's body, which only a call runs, never an import."""

from textwrap import dedent

import pytest

from coverage_checks.function_bodies import find_function_body_lines


@pytest.mark.parametrize(
    "source,body_lines",
    [
        (
            """\
            import os

            def separator(is_posix):
                if is_posix:
                    return os.sep
                return "/"
            """,
            {4, 5, 6},
        ),
        (
            """\
            @cache
            def scaled(
                size: int = DEFAULT_SIZE,
            ) -> int:
                return size * 2
            """,
            {5},
        ),
        (
            """\
            class Reader:
                size = 3

                def read(self):
                    return self.size

                async def wait(self):
                    await ready()
            """,
            {5, 8},
        ),
    ],
    ids=["function", "decorated-multi-line-signature", "class"],
)
def test_a_body_is_in_and_what_import_runs_is_not(source: str, body_lines: set[int]) -> None:
    assert find_function_body_lines(dedent(source)) == body_lines


def test_a_nested_def_line_runs_with_its_enclosing_function() -> None:
    source = """\
        def outer():
            def inner():
                return 1
            return inner
        """
    assert find_function_body_lines(dedent(source)) == {2, 3, 4}


def test_a_one_line_def_runs_at_import() -> None:
    source = """\
        class Port(Protocol):
            def read(self) -> bytes: ...
        """
    assert find_function_body_lines(dedent(source)) == set()


@pytest.mark.parametrize(
    "source",
    [
        """\
        try:
            import fast
        except ImportError:
            def speed():
                return 0
        """,
        """\
        if fast:
            import fast
        else:
            def speed():
                return 0
        """,
    ],
    ids=["except", "else"],
)
def test_a_function_under_any_module_level_statement_is_found(source: str) -> None:
    assert find_function_body_lines(dedent(source)) == {5}
