from pathlib import PurePath

from template_checks.application.ports.driving.template_attribute_lister import (
    TemplateAttributeListing,
)
from template_checks.application.use_cases.list_template_attributes import ListTemplateAttributes
from tests.fakes.adapters.driven.fake_template_reader import FakeTemplateReader


def test_list_template_attributes_lists_what_the_directory_s_templates_read() -> None:
    template_reader = FakeTemplateReader(
        PurePath("/templates"),
        templates_by_path={
            PurePath("files.html"): "{{ nav.prev_url }}",
            PurePath("row.html"): "{{ row.filename }}",
        },
    )

    template_attribute_listing = ListTemplateAttributes(
        template_reader=template_reader
    ).list_template_attributes(PurePath("/templates"))

    assert template_attribute_listing == TemplateAttributeListing(
        template_attributes=frozenset({"prev_url", "filename"})
    )
