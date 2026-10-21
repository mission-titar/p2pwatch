"""Tests for the logic-free check's entry function, over a templates directory."""

from pathlib import Path

import pytest

from template_checks.adapters.driving.check_templates import main


def test_main_returns_0_and_prints_nothing_on_logic_free_templates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "clean.html").write_text(
        "{% extends 'base.html' %}{% block content %}{{ page.title }}{% endblock %}"
    )

    assert main(tmp_path) == 0

    assert capsys.readouterr().out == ""


def test_main_returns_1_and_prints_the_constructs_of_every_html_file_at_any_depth(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "nested.html").write_text("{{ a|upper }}")
    (tmp_path / "bad.html").write_text("{% if x %}oops{% endif %}")
    (tmp_path / "readme.txt").write_text("{% if x %}oops{% endif %}")

    assert main(tmp_path) == 1

    assert capsys.readouterr().out == (
        "bad.html:1: If is not logic-free\npages/nested.html:1: Filter is not logic-free\n"
    )
