"""Tests for a template's syntax tree, a template Jinja cannot parse being a broken input."""

from pathlib import PurePath

import pytest
from jinja2 import nodes

from template_checks.domain.broken_input_error import BrokenInputError
from template_checks.domain.template_parsing import parse_template


def test_parse_template_returns_the_template_s_syntax_tree() -> None:
    template = parse_template(PurePath("page.html"), template_text="{{ page.title }}")

    assert [node.attr for node in template.find_all(nodes.Getattr)] == ["title"]


def test_a_template_jinja_cannot_parse_raises_a_broken_input_naming_it_and_its_line() -> None:
    with pytest.raises(
        BrokenInputError, match=r"^pages/node\.html:2: Encountered unknown tag 'elif'\.$"
    ):
        parse_template(PurePath("pages/node.html"), template_text="<p>\n{% elif x %}a")
