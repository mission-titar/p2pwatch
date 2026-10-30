from vex_checks.domain.claim_problem import ClaimProblem
from vex_checks.domain.claims import evaluate_claim_coverage, merge_claims

NOT_PRESENT = "vulnerable_code_not_present"
NOT_IN_EXECUTE_PATH = "vulnerable_code_not_in_execute_path"


def test_merge_claims_unites_the_claims_of_each_vex() -> None:
    merged = merge_claims(
        [
            {"CVE-1": "vulnerable_code_not_present"},
            {"CVE-2": "vulnerable_code_not_in_execute_path"},
        ]
    )
    assert merged == {
        "CVE-1": frozenset({"vulnerable_code_not_present"}),
        "CVE-2": frozenset({"vulnerable_code_not_in_execute_path"}),
    }


def test_merge_claims_keeps_one_justification_two_vex_agree_on() -> None:
    claims = {"CVE-SHARED": "vulnerable_code_not_present"}
    assert merge_claims([claims, claims]) == {
        "CVE-SHARED": frozenset({"vulnerable_code_not_present"})
    }


def test_merge_claims_keeps_both_justifications_of_one_advisory() -> None:
    merged = merge_claims(
        [
            {"CVE-SHARED": "vulnerable_code_not_present"},
            {"CVE-SHARED": "vulnerable_code_not_in_execute_path"},
        ]
    )
    assert merged == {
        "CVE-SHARED": frozenset(
            {"vulnerable_code_not_present", "vulnerable_code_not_in_execute_path"}
        )
    }


def test_claims_each_backed_by_its_image_premise_or_source_rule_are_no_problem() -> None:
    justifications_by_advisory_id = {
        "CVE-IMAGE": frozenset({NOT_PRESENT}),
        "CVE-SOURCE": frozenset({NOT_IN_EXECUTE_PATH}),
    }

    assert (
        evaluate_claim_coverage(
            justifications_by_advisory_id,
            image_premise_ids={"CVE-IMAGE"},
            source_rule_ids={"CVE-SOURCE"},
        )
        == []
    )


def test_a_claim_with_neither_an_image_premise_nor_a_source_rule_is_a_problem() -> None:
    assert evaluate_claim_coverage(
        {"CVE-A": frozenset({NOT_PRESENT})}, image_premise_ids=set(), source_rule_ids=set()
    ) == [ClaimProblem(advisory_id="CVE-A", message="claim has no premise or source rule")]


def test_an_image_premise_without_a_claim_is_a_problem() -> None:
    assert evaluate_claim_coverage({}, image_premise_ids={"CVE-A"}, source_rule_ids=set()) == [
        ClaimProblem(advisory_id="CVE-A", message="premise has no claim")
    ]


def test_a_source_rule_without_a_claim_is_a_problem() -> None:
    assert evaluate_claim_coverage({}, image_premise_ids=set(), source_rule_ids={"CVE-A"}) == [
        ClaimProblem(advisory_id="CVE-A", message="source rule has no claim")
    ]


def test_a_justification_other_than_its_backing_s_is_a_problem() -> None:
    justifications_by_advisory_id = {
        "CVE-IMAGE": frozenset({NOT_IN_EXECUTE_PATH}),
        "CVE-SOURCE": frozenset({NOT_PRESENT}),
    }

    assert evaluate_claim_coverage(
        justifications_by_advisory_id,
        image_premise_ids={"CVE-IMAGE"},
        source_rule_ids={"CVE-SOURCE"},
    ) == [
        ClaimProblem(
            advisory_id="CVE-IMAGE",
            message="justification 'vulnerable_code_not_in_execute_path'"
            " is not 'vulnerable_code_not_present'",
        ),
        ClaimProblem(
            advisory_id="CVE-SOURCE",
            message="justification 'vulnerable_code_not_present'"
            " is not 'vulnerable_code_not_in_execute_path'",
        ),
    ]


def test_an_id_with_both_an_image_premise_and_a_source_rule_is_a_problem() -> None:
    assert evaluate_claim_coverage(
        {"CVE-A": frozenset({NOT_PRESENT})}, image_premise_ids={"CVE-A"}, source_rule_ids={"CVE-A"}
    ) == [ClaimProblem(advisory_id="CVE-A", message="has both an image premise and a source rule")]


def test_an_advisory_justified_differently_across_vex_files_is_a_problem() -> None:
    justifications_by_advisory_id = {"CVE-IMAGE": frozenset({NOT_IN_EXECUTE_PATH, NOT_PRESENT})}

    assert evaluate_claim_coverage(
        justifications_by_advisory_id, image_premise_ids={"CVE-IMAGE"}, source_rule_ids=set()
    ) == [
        ClaimProblem(
            advisory_id="CVE-IMAGE",
            message="justification 'vulnerable_code_not_in_execute_path'"
            " is not 'vulnerable_code_not_present'",
        ),
        ClaimProblem(advisory_id="CVE-IMAGE", message="justified differently across VEX files"),
    ]


def test_the_problems_are_in_the_order_of_their_advisory_ids_then_messages() -> None:
    justifications_by_advisory_id = {
        "CVE-B": frozenset({NOT_PRESENT}),
        "CVE-A": frozenset({NOT_PRESENT, NOT_IN_EXECUTE_PATH}),
    }

    assert evaluate_claim_coverage(
        justifications_by_advisory_id, image_premise_ids=set(), source_rule_ids=set()
    ) == [
        ClaimProblem(advisory_id="CVE-A", message="claim has no premise or source rule"),
        ClaimProblem(advisory_id="CVE-A", message="justified differently across VEX files"),
        ClaimProblem(advisory_id="CVE-B", message="claim has no premise or source rule"),
    ]
