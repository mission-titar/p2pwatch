from pathlib import PurePath

from template_checks.application.ports.driving.logic_free_checker import LogicFreeReport
from template_checks.application.use_cases.check_logic_free import CheckLogicFree
from template_checks.domain.logic_constructs import RefusedNode
from tests.fakes.adapters.driven.fake_template_reader import FakeTemplateReader


def test_check_logic_free_reports_the_constructs_of_the_directory_s_templates() -> None:
    template_reader = FakeTemplateReader(
        PurePath("/templates"),
        templates_by_path={
            PurePath("base.html"): "{{ a or b }}",
            PurePath("pages/files.html"): "{{ page.title }}",
            PurePath("pages/node.html"): "{% if x %}a{% endif %}",
        },
    )

    logic_free_report = CheckLogicFree(template_reader=template_reader).check_logic_free(
        PurePath("/templates")
    )

    assert logic_free_report == LogicFreeReport(
        problems=(
            RefusedNode(template_path=PurePath("base.html"), line_number=1, node_type="Or"),
            RefusedNode(template_path=PurePath("pages/node.html"), line_number=1, node_type="If"),
        )
    )


def test_check_logic_free_of_logic_free_templates_reports_no_problem() -> None:
    template_reader = FakeTemplateReader(
        PurePath("/templates"), templates_by_path={PurePath("page.html"): "{{ page.title }}"}
    )

    logic_free_report = CheckLogicFree(template_reader=template_reader).check_logic_free(
        PurePath("/templates")
    )

    assert logic_free_report == LogicFreeReport(problems=())
