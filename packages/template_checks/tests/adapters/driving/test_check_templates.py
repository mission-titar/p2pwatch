"""Tests for the logic-free Jinja2 template guard (token-match)."""

from pathlib import Path

import pytest

from template_checks.adapters.driving.check_templates import find_logic_violations, main


def test_clean_template_has_no_violation(tmp_path: Path) -> None:
    """A compliant template (extends + for + attribute access) triggers no violation."""
    (tmp_path / "ok.html").write_text(
        "{% extends 'base.html' %}"
        "{% block content %}"
        "<ul>{% for f in files %}<li>{{ f.name }}</li>{% endfor %}</ul>"
        "{% endblock %}"
    )
    assert find_logic_violations(tmp_path) == []


def test_clean_template_with_else_has_no_violation(tmp_path: Path) -> None:
    """{% for %}…{% else %}…{% endfor %} is allowed."""
    (tmp_path / "ok2.html").write_text(
        "{% for f in files %}<li>{{ f.name }}</li>{% else %}<li>nothing</li>{% endfor %}"
    )
    assert find_logic_violations(tmp_path) == []


def test_clean_template_simple_var_has_no_violation(tmp_path: Path) -> None:
    """Simple {{ x }} and {{ x.attr.sub }} are allowed."""
    (tmp_path / "ok3.html").write_text("<p>{{ title }}</p><p>{{ node.status.label }}</p>")
    assert find_logic_violations(tmp_path) == []


@pytest.mark.parametrize(
    "body,reason_fragment",
    [
        ("{% if x %}a{% endif %}", "if"),
        ("{% elif x %}a", "elif"),
        ("{% set y = 1 %}", "set"),
        ("{% macro m() %}{% endmacro %}", "macro"),
        ("{{ a + b }}", "expression"),
        ("{{ a - b }}", "expression"),
        ("{{ a * b }}", "expression"),
        ("{{ a / b }}", "expression"),
        ("{{ a % b }}", "expression"),
        ("{{ a == b }}", "expression"),
        ("{{ a != b }}", "expression"),
        ("{{ a < b }}", "expression"),
        ("{{ a > b }}", "expression"),
        ("{{ items|length }}", "expression"),
        ("{{ func() }}", "expression"),
    ],
)
def test_forbidden_constructs_are_flagged(tmp_path: Path, body: str, reason_fragment: str) -> None:
    """Each forbidden construct must produce at least one violation."""
    (tmp_path / "bad.html").write_text(body)
    violations = find_logic_violations(tmp_path)
    assert violations != [], f"expected violation for {body!r}"
    assert any(reason_fragment in v for v in violations), (
        f"expected '{reason_fragment}' in violations {violations!r}"
    )


def test_returns_filename_in_violation(tmp_path: Path) -> None:
    """The violations list contains the file name."""
    (tmp_path / "mytemplate.html").write_text("{% if x %}oops{% endif %}")
    violations = find_logic_violations(tmp_path)
    assert any("mytemplate.html" in v for v in violations)


def test_scans_subdirectories(tmp_path: Path) -> None:
    """Subdirectories are scanned recursively."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.html").write_text("{% if x %}oops{% endif %}")
    violations = find_logic_violations(tmp_path)
    assert violations != []


def test_ignores_non_html_files(tmp_path: Path) -> None:
    """Non-HTML files (e.g. .txt) are ignored."""
    (tmp_path / "readme.txt").write_text("{% if x %}oops{% endif %}")
    assert find_logic_violations(tmp_path) == []


def test_empty_directory_has_no_violation(tmp_path: Path) -> None:
    """An empty directory returns an empty list."""
    assert find_logic_violations(tmp_path) == []


def test_main_returns_0_when_no_violations(tmp_path: Path) -> None:
    """main() returns 0 when there is no violation."""
    (tmp_path / "clean.html").write_text(
        "{% extends 'base.html' %}{% block content %}{% endblock %}"
    )
    assert main(tmp_path) == 0


def test_main_returns_1_and_prints_the_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() returns 1 and prints the violations when there are any."""
    (tmp_path / "bad.html").write_text("{% if x %}oops{% endif %}")
    assert main(tmp_path) == 1
    assert "bad.html" in capsys.readouterr().out
