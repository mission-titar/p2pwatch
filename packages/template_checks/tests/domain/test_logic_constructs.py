"""Tests for the logic constructs a template holds, read from Jinja's syntax tree."""

from pathlib import PurePath

import pytest

from template_checks.domain.logic_constructs import find_logic_constructs

_PAGE = PurePath("page.html")


@pytest.mark.parametrize(
    "template_text",
    [
        "<p>plain text</p>",
        "{{ title }}",
        "{{ node.status.label }}",
        "{% for f in page.files %}<li>{{ f.filename }}</li>{% endfor %}",
        "{% for f in files %}{{ f.filename }}{% else %}<li>nothing</li>{% endfor %}",
        "{% extends 'base.html' %}{% block content %}{{ page.title }}{% endblock %}",
        "{% include 'nav.html' %}",
        "{% include page.nav_template %}",
        "{# a comment #}{% raw %}{{ shown as text }}{% endraw %}",
    ],
)
def test_a_logic_free_template_holds_no_logic_construct(template_text: str) -> None:
    assert find_logic_constructs({_PAGE: template_text}) == ()


@pytest.mark.parametrize(
    "template_text,construct",
    [
        ("{{ a ~ b }}", "Concat"),
        ("{{ a if b else c }}", "CondExpr"),
        ("{{ rows[first] }}", "Getitem"),
        ("{{ a and b }}", "And"),
        ("{{ a is defined }}", "Test"),
        ("{% with x = y %}{{ x }}{% endwith %}", "With"),
        ("{% call m() %}x{% endcall %}", "CallBlock"),
        ("{% for f in files if f %}{% endfor %}", "For with an if filter"),
        ("{% if x %}a{% endif %}", "If"),
        ("{% set y = x %}", "Assign"),
        ("{% macro m() %}{% endmacro %}", "Macro"),
        ("{{ a + b }}", "Add"),
        ("{{ a != b }}", "Compare"),
        ("{{ files|length }}", "Filter"),
        ("{{ f() }}", "Call"),
        ("{{ 'text' }}", "Const"),
        ("{% for a, b in pairs %}{% endfor %}", "Tuple"),
        ("{% include ['a.html', 'b.html'] %}", "List"),
    ],
)
def test_each_logic_construct_is_found_first_with_its_line(
    template_text: str, construct: str
) -> None:
    problems = find_logic_constructs({_PAGE: f"<p>\n{template_text}"})

    assert problems[0] == f"page.html:2: {construct} is not logic-free"


def test_a_construct_inside_another_is_found_too() -> None:
    assert find_logic_constructs({_PAGE: "{% if x %}{{ a|upper }}{% endif %}"}) == (
        "page.html:1: If is not logic-free",
        "page.html:1: Filter is not logic-free",
    )


def test_the_constructs_of_every_template_are_found_under_their_relative_paths() -> None:
    templates_by_path = {
        PurePath("base.html"): "{{ a or b }}",
        PurePath("pages/files.html"): "{{ page.title }}",
        PurePath("pages/node.html"): "{{ -size }}",
    }

    assert find_logic_constructs(templates_by_path) == (
        "base.html:1: Or is not logic-free",
        "pages/node.html:1: Neg is not logic-free",
    )


def test_a_template_jinja_cannot_parse_is_a_problem_naming_its_error() -> None:
    assert find_logic_constructs({_PAGE: "<p>\n{% elif x %}a"}) == (
        "page.html:2: Encountered unknown tag 'elif'.",
    )
