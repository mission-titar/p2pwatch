"""Tests for the attribute names templates read, which vulture cannot see."""

from pathlib import PurePath

import pytest

from template_checks.domain.broken_input_error import BrokenInputError
from template_checks.domain.template_attributes import find_template_attributes

_PAGE = PurePath("page.html")


@pytest.mark.parametrize(
    "template_text,template_attributes",
    [
        ("{{ row.best_tier_display }}", {"best_tier_display"}),
        ("{{ node.status.label }}", {"status", "label"}),
        ("{% for f in page.files %}{{ f.filename }}{% endfor %}", {"files", "filename"}),
    ],
)
def test_each_attribute_a_template_reads_is_found(
    template_text: str, template_attributes: set[str]
) -> None:
    assert find_template_attributes({_PAGE: template_text}) == template_attributes


def test_a_template_without_attribute_reads_finds_nothing() -> None:
    assert find_template_attributes({_PAGE: "{{ title }}"}) == frozenset()


def test_the_attributes_of_every_template_are_found() -> None:
    templates_by_path = {
        PurePath("files.html"): "{{ nav.prev_url }}",
        PurePath("row.html"): "{{ row.filename }}",
    }

    assert find_template_attributes(templates_by_path) == {"prev_url", "filename"}


def test_a_template_jinja_cannot_parse_raises_a_broken_input_naming_it() -> None:
    with pytest.raises(BrokenInputError, match=r"^page\.html:1: "):
        find_template_attributes({_PAGE: "{% if %}"})
