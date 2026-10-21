from pathlib import PurePath

from template_checks.application.list_template_attributes import ListTemplateAttributes
from template_checks.ports.driving.template_attribute_lister import TemplateAttributeListing
from tests.fakes import FakeTemplateReader


def test_list_template_attributes_lists_what_the_directory_s_templates_read() -> None:
    template_reader = FakeTemplateReader(
        PurePath("/templates"),
        {PurePath("files.html"): "{{ nav.prev_url }}", PurePath("row.html"): "{{ row.filename }}"},
    )

    template_attribute_listing = ListTemplateAttributes(
        template_reader=template_reader
    ).list_template_attributes(PurePath("/templates"))

    assert template_attribute_listing == TemplateAttributeListing(
        template_attributes=frozenset({"prev_url", "filename"})
    )
