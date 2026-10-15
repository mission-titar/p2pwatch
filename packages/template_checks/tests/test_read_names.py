"""Tests for the attribute names the webui's templates read, handed to vulture."""

from pathlib import Path
from unittest.mock import patch

import pytest

from template_checks.read_names import find_read_names, main


@pytest.mark.parametrize(
    "body,read_names",
    [
        ("{{ row.best_tier_display }}", {"best_tier_display"}),
        ("{{ node.status.label }}", {"status", "label"}),
        ("{% for f in page.files %}{{ f.filename }}{% endfor %}", {"files", "filename"}),
    ],
)
def test_each_attribute_a_template_reads_is_found(
    tmp_path: Path, body: str, read_names: set[str]
) -> None:
    (tmp_path / "page.html").write_text(body)
    assert find_read_names(tmp_path) == read_names


def test_a_template_without_attribute_reads_finds_nothing(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text("{{ title }}")
    assert find_read_names(tmp_path) == frozenset()


def test_templates_in_subdirectories_are_read_and_other_files_are_not(tmp_path: Path) -> None:
    (tmp_path / "base.html").write_text("{{ nav.prev_url }}")
    (tmp_path / "partials").mkdir()
    (tmp_path / "partials" / "row.html").write_text("{{ row.filename }}")
    (tmp_path / "notes.txt").write_text("{{ row.ignored }}")
    assert find_read_names(tmp_path) == {"prev_url", "filename"}


def test_main_prints_the_names_sorted_and_comma_joined(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "page.html").write_text("{{ row.size_mib }}{{ row.filename }}")
    with patch("sys.argv", ["read_names", str(tmp_path)]):
        main()
    assert capsys.readouterr().out == "filename,size_mib\n"


def test_main_exits_with_usage_when_no_arg() -> None:
    with patch("sys.argv", ["read_names"]), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == "usage: read_names <templates dir>"
