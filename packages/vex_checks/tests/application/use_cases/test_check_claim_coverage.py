"""CheckClaimCoverage: the claims of every VEX, the registry's image premises and the source
rules, read and handed to their bijection."""

from pathlib import PurePath

from tests.fakes.adapters.driven.fake_source_rule_reader import FakeSourceRuleReader
from tests.fakes.adapters.driven.fake_vex_reader import FakeVexReader
from vex_checks.application.use_cases.check_claim_coverage import CheckClaimCoverage
from vex_checks.domain.claim_problem import ClaimProblem
from vex_checks.domain.descriptors import DpkgPackageAbsent

CRAWLER_VEX = PurePath("/repo/security/crawler.vex.openvex.json")
AMULE_VEX = PurePath("/repo/security/amule.vex.openvex.json")
NOT_PRESENT = "vulnerable_code_not_present"
NOT_IN_EXECUTE_PATH = "vulnerable_code_not_in_execute_path"


def test_claims_each_backed_by_its_image_premise_or_source_rule_are_no_problem() -> None:
    checker = CheckClaimCoverage(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        vex_paths=(CRAWLER_VEX,),
        vex_reader=FakeVexReader({"CVE-IMAGE": NOT_PRESENT, "CVE-SOURCE": NOT_IN_EXECUTE_PATH}),
        source_rule_reader=FakeSourceRuleReader({"CVE-SOURCE"}),
    )

    assert checker.check_claim_coverage().problems == ()


def test_the_image_premises_and_the_source_rules_are_checked_against_the_claims() -> None:
    checker = CheckClaimCoverage(
        premises={"CVE-IMAGE": DpkgPackageAbsent("nghttp2")},
        vex_paths=(CRAWLER_VEX,),
        vex_reader=FakeVexReader({}),
        source_rule_reader=FakeSourceRuleReader({"CVE-SOURCE"}),
    )

    assert checker.check_claim_coverage().problems == (
        ClaimProblem("CVE-IMAGE", "premise has no claim"),
        ClaimProblem("CVE-SOURCE", "source rule has no claim"),
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
        ClaimProblem("CVE-UNBACKED", "claim has no premise or source rule"),
    )
