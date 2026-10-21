"""CheckClaimCoverage: the claims in bijection with the image premises and the source rules."""

from collections.abc import Mapping
from pathlib import PurePath

from tests.fakes import FakeSourceRuleReader, FakeVexReader
from vex_checks.application.check_claim_coverage import CheckClaimCoverage
from vex_checks.domain.descriptors import DpkgPackageAbsent, ImagePremise
from vex_checks.ports.driving.claim_coverage_checker import ClaimCoverageProblem

CRAWLER_VEX = PurePath("/repo/security/crawler.vex.openvex.json")
AMULE_VEX = PurePath("/repo/security/amule.vex.openvex.json")
NOT_PRESENT = "vulnerable_code_not_present"
NOT_IN_EXECUTE_PATH = "vulnerable_code_not_in_execute_path"


def _checker(
    *,
    premises: Mapping[str, ImagePremise],
    claims: dict[str, str],
    source_rule_ids: set[str],
) -> CheckClaimCoverage:
    return CheckClaimCoverage(
        premises=premises,
        vex_paths=(CRAWLER_VEX,),
        vex_reader=FakeVexReader(claims),
        source_rule_reader=FakeSourceRuleReader(source_rule_ids),
    )


def test_claims_each_backed_by_its_image_premise_or_source_rule_are_no_problem() -> None:
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        claims={"CVE-IMAGE": NOT_PRESENT, "CVE-SOURCE": NOT_IN_EXECUTE_PATH},
        source_rule_ids={"CVE-SOURCE"},
    )

    assert checker.check_claim_coverage().problems == ()


def test_a_claim_with_neither_an_image_premise_nor_a_source_rule_is_a_problem() -> None:
    checker = _checker(premises={}, claims={"CVE-A": NOT_PRESENT}, source_rule_ids=set())

    assert checker.check_claim_coverage().problems == (
        ClaimCoverageProblem("CVE-A", "claim has no premise or source rule"),
    )


def test_an_image_premise_without_a_claim_is_a_problem() -> None:
    checker = _checker(
        premises={"CVE-A": DpkgPackageAbsent("nghttp2")}, claims={}, source_rule_ids=set()
    )

    assert checker.check_claim_coverage().problems == (
        ClaimCoverageProblem("CVE-A", "premise has no claim"),
    )


def test_a_source_rule_without_a_claim_is_a_problem() -> None:
    checker = _checker(premises={}, claims={}, source_rule_ids={"CVE-A"})

    assert checker.check_claim_coverage().problems == (
        ClaimCoverageProblem("CVE-A", "source rule has no claim"),
    )


def test_a_justification_other_than_its_backing_s_is_a_problem() -> None:
    checker = _checker(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        claims={"CVE-IMAGE": NOT_IN_EXECUTE_PATH, "CVE-SOURCE": NOT_PRESENT},
        source_rule_ids={"CVE-SOURCE"},
    )

    assert checker.check_claim_coverage().problems == (
        ClaimCoverageProblem(
            "CVE-IMAGE",
            "justification 'vulnerable_code_not_in_execute_path'"
            " is not 'vulnerable_code_not_present'",
        ),
        ClaimCoverageProblem(
            "CVE-SOURCE",
            "justification 'vulnerable_code_not_present'"
            " is not 'vulnerable_code_not_in_execute_path'",
        ),
    )


def test_an_id_with_both_an_image_premise_and_a_source_rule_is_a_problem() -> None:
    checker = _checker(
        premises={"CVE-A": DpkgPackageAbsent("nghttp2")},
        claims={"CVE-A": NOT_PRESENT},
        source_rule_ids={"CVE-A"},
    )

    assert checker.check_claim_coverage().problems == (
        ClaimCoverageProblem("CVE-A", "has both an image premise and a source rule"),
    )


def test_the_claims_of_every_vex_are_checked() -> None:
    checker = CheckClaimCoverage(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        vex_paths=(CRAWLER_VEX, AMULE_VEX),
        vex_reader=FakeVexReader(
            {},
            claims_by_vex_path={
                CRAWLER_VEX: {"CVE-SOURCE": NOT_IN_EXECUTE_PATH},
                AMULE_VEX: {"CVE-IMAGE": NOT_PRESENT, "CVE-UNBACKED": NOT_PRESENT},
            },
        ),
        source_rule_reader=FakeSourceRuleReader({"CVE-SOURCE"}),
    )

    assert checker.check_claim_coverage().problems == (
        ClaimCoverageProblem("CVE-UNBACKED", "claim has no premise or source rule"),
    )


def test_an_advisory_justified_differently_across_vex_files_is_a_problem() -> None:
    checker = CheckClaimCoverage(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        vex_paths=(CRAWLER_VEX, AMULE_VEX),
        vex_reader=FakeVexReader(
            {},
            claims_by_vex_path={
                CRAWLER_VEX: {"CVE-IMAGE": NOT_IN_EXECUTE_PATH},
                AMULE_VEX: {"CVE-IMAGE": NOT_PRESENT},
            },
        ),
        source_rule_reader=FakeSourceRuleReader(set()),
    )

    assert checker.check_claim_coverage().problems == (
        ClaimCoverageProblem(
            "CVE-IMAGE",
            "justification 'vulnerable_code_not_in_execute_path'"
            " is not 'vulnerable_code_not_present'",
        ),
        ClaimCoverageProblem("CVE-IMAGE", "justified differently across VEX files"),
    )


def test_the_problems_are_in_the_order_of_their_advisory_ids() -> None:
    checker = _checker(
        premises={}, claims={"CVE-B": NOT_PRESENT, "CVE-A": NOT_PRESENT}, source_rule_ids=set()
    )

    assert [problem.advisory_id for problem in checker.check_claim_coverage().problems] == [
        "CVE-A",
        "CVE-B",
    ]
