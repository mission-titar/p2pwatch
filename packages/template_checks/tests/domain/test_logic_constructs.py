"""Tests for the logic constructs a template holds, read from Jinja's syntax tree."""

from pathlib import PurePath

import pytest

from template_checks.domain.broken_input_error import BrokenInputError
from template_checks.domain.logic_constructs import (
    FilteredLoop,
    RefusedNode,
    find_logic_constructs,
)

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
    "template_text,node_type",
    [
        ("{{ a ~ b }}", "Concat"),
        ("{{ a if b else c }}", "CondExpr"),
        ("{{ rows[first] }}", "Getitem"),
        ("{{ a and b }}", "And"),
        ("{{ a is defined }}", "Test"),
        ("{% with x = y %}{{ x }}{% endwith %}", "With"),
        ("{% call m() %}x{% endcall %}", "CallBlock"),
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
def test_each_refused_node_is_found_first_with_its_line(
    *, template_text: str, node_type: str
) -> None:
    logic_constructs = find_logic_constructs({_PAGE: f"<p>\n{template_text}"})

    assert logic_constructs[0] == RefusedNode(
        template_path=_PAGE, line_number=2, node_type=node_type
    )


def test_a_loop_with_an_if_filter_is_found_with_its_line() -> None:
    logic_constructs = find_logic_constructs({_PAGE: "<p>\n{% for f in files if f %}{% endfor %}"})

    assert logic_constructs == (FilteredLoop(template_path=_PAGE, line_number=2),)


def test_a_construct_inside_another_is_found_too() -> None:
    assert find_logic_constructs({_PAGE: "{% if x %}{{ a|upper }}{% endif %}"}) == (
        RefusedNode(template_path=_PAGE, line_number=1, node_type="If"),
        RefusedNode(template_path=_PAGE, line_number=1, node_type="Filter"),
    )


def test_the_constructs_of_every_template_are_found_under_their_relative_paths() -> None:
    templates_by_path = {
        PurePath("base.html"): "{{ a or b }}",
        PurePath("pages/files.html"): "{{ page.title }}",
        PurePath("pages/node.html"): "{{ -size }}",
    }

    assert find_logic_constructs(templates_by_path) == (
        RefusedNode(template_path=PurePath("base.html"), line_number=1, node_type="Or"),
        RefusedNode(template_path=PurePath("pages/node.html"), line_number=1, node_type="Neg"),
    )


def test_a_template_jinja_cannot_parse_raises_a_broken_input_naming_it() -> None:
    with pytest.raises(BrokenInputError, match=r"^page\.html:2: "):
        find_logic_constructs({_PAGE: "<p>\n{% elif x %}a"})
