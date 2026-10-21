from pathlib import PurePath

from template_checks.application.list_template_attributes import ListTemplateAttributes
from template_checks.ports.driven.template_reader import TemplateReader
from template_checks.ports.driving.template_attribute_lister import TemplateAttributeListing


class FakeTemplateReader(TemplateReader):
    """Holds the templates of one directory, by their path relative to it."""

    def __init__(self, templates_directory: PurePath, *template_texts: str) -> None:
        self._templates_directory = templates_directory
        self._template_texts = template_texts

    def read_templates(self, templates_directory: PurePath) -> dict[PurePath, str]:
        assert templates_directory == self._templates_directory
        return {
            PurePath(f"page_{index}.html"): template_text
            for index, template_text in enumerate(self._template_texts)
        }


def test_list_template_attributes_lists_what_the_directory_s_templates_read() -> None:
    template_reader = FakeTemplateReader(
        PurePath("/templates"), "{{ nav.prev_url }}", "{{ row.filename }}"
    )

    template_attribute_listing = ListTemplateAttributes(
        template_reader=template_reader
    ).list_template_attributes(PurePath("/templates"))

    assert template_attribute_listing == TemplateAttributeListing(
        template_attributes=frozenset({"prev_url", "filename"})
    )
