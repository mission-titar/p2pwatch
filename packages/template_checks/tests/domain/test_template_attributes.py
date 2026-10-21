"""Tests for the attribute names templates read, which vulture cannot see."""

import pytest

from template_checks.domain.template_attributes import find_template_attributes


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
    assert find_template_attributes([template_text]) == template_attributes


def test_a_template_without_attribute_reads_finds_nothing() -> None:
    assert find_template_attributes(["{{ title }}"]) == frozenset()


def test_the_attributes_of_every_template_are_found() -> None:
    assert find_template_attributes(["{{ nav.prev_url }}", "{{ row.filename }}"]) == {
        "prev_url",
        "filename",
    }
