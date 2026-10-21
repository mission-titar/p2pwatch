"""Tests for the attribute names the webui's templates read, handed to vulture."""

from pathlib import Path, PurePath

import pytest

from template_checks.adapters.driving.read_names import find_read_names, main
from template_checks.ports.driven.template_reader import TemplateReader


class _FakeTemplateReader(TemplateReader):
    """Holds the templates of one directory, by their path relative to it."""

    def __init__(self, templates_directory: PurePath, *texts: str) -> None:
        self._templates_directory = templates_directory
        self._texts = texts

    def read_templates(self, templates_directory: PurePath) -> dict[PurePath, str]:
        assert templates_directory == self._templates_directory
        return {PurePath(f"page_{index}.html"): text for index, text in enumerate(self._texts)}


@pytest.mark.parametrize(
    "body,read_names",
    [
        ("{{ row.best_tier_display }}", {"best_tier_display"}),
        ("{{ node.status.label }}", {"status", "label"}),
        ("{% for f in page.files %}{{ f.filename }}{% endfor %}", {"files", "filename"}),
    ],
)
def test_each_attribute_a_template_reads_is_found(body: str, read_names: set[str]) -> None:
    template_reader = _FakeTemplateReader(Path("templates"), body)

    assert find_read_names(Path("templates"), template_reader=template_reader) == read_names


def test_a_template_without_attribute_reads_finds_nothing() -> None:
    template_reader = _FakeTemplateReader(Path("templates"), "{{ title }}")

    assert find_read_names(Path("templates"), template_reader=template_reader) == frozenset()


def test_the_names_of_every_template_are_found() -> None:
    template_reader = _FakeTemplateReader(
        Path("templates"), "{{ nav.prev_url }}", "{{ row.filename }}"
    )

    assert find_read_names(Path("templates"), template_reader=template_reader) == {
        "prev_url",
        "filename",
    }


def test_main_prints_the_names_sorted_and_comma_joined(
    capsys: pytest.CaptureFixture[str],
) -> None:
    template_reader = _FakeTemplateReader(Path("templates"), "{{ row.size_mib }}{{ row.filename }}")

    main(Path("templates"), template_reader=template_reader)

    assert capsys.readouterr().out == "filename,size_mib\n"
