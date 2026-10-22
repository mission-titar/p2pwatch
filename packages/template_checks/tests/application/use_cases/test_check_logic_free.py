from pathlib import PurePath

from template_checks.application.ports.driving.logic_free_checker import LogicFreeReport
from template_checks.application.use_cases.check_logic_free import CheckLogicFree
from tests.fakes.adapters.driven.fake_template_reader import FakeTemplateReader


def test_check_logic_free_reports_the_constructs_of_the_directory_s_templates() -> None:
    template_reader = FakeTemplateReader(
        PurePath("/templates"),
        {
            PurePath("base.html"): "{{ a or b }}",
            PurePath("pages/files.html"): "{{ page.title }}",
            PurePath("pages/node.html"): "{% if x %}a{% endif %}",
        },
    )

    logic_free_report = CheckLogicFree(template_reader=template_reader).check_logic_free(
        PurePath("/templates")
    )

    assert logic_free_report == LogicFreeReport(
        problems=("base.html:1: Or is not logic-free", "pages/node.html:1: If is not logic-free")
    )


def test_check_logic_free_of_logic_free_templates_reports_no_problem() -> None:
    template_reader = FakeTemplateReader(
        PurePath("/templates"), {PurePath("page.html"): "{{ page.title }}"}
    )

    logic_free_report = CheckLogicFree(template_reader=template_reader).check_logic_free(
        PurePath("/templates")
    )

    assert logic_free_report == LogicFreeReport(problems=())
