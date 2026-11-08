from pathlib import PurePath

import pytest

from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.matching.config import (
    AllDefinition,
    AnyDefinition,
    Condition,
    CoverageDefinition,
    KeywordDefinition,
    MatcherConfig,
    NotDefinition,
    RegexDefinition,
    Rule,
    TokenDefinition,
    TokenReference,
)
from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.models import TargetSegment
from p2pwatch.domain.matching.validation import (
    CycleError,
    DepthExceededError,
    MatchingConfigError,
    TargetDuplicate,
    UnknownTokenError,
    duplicate_targets,
    expand_fragments,
    fragment_problems,
    has_control_character,
    validate_config,
)

_FILE = PurePath("/srv/matcher.yml")
_KERORO = KeywordDefinition(phrase="keroro")
_COVERAGE = CoverageDefinition(reference="title", min_coverage=0.5)


def _rule(condition: Condition) -> Rule:
    return Rule(name="r", tier=DecisionTier.CATALOG, scope="unattributed", condition=condition)


def _chain(length: int) -> dict[str, TokenDefinition]:
    """``t0`` a keyword, each ``t<i>`` up to ``t<length - 1>`` citing ``t<i - 1>``."""
    chain: dict[str, TokenDefinition] = {"t0": KeywordDefinition(phrase="x")}
    for index in range(1, length):
        chain[f"t{index}"] = AnyDefinition(operands=(f"t{index - 1}",))
    return chain


def test_override_on_non_coverage_token_raises() -> None:
    rule = _rule(AllDefinition(operands=(TokenReference(name="kw", min_coverage=0.5),)))
    with pytest.raises(MatchingConfigError, match="kw"):
        validate_config(MatcherConfig(tokens={"kw": _KERORO}, rules=(rule,)))


# A format character such as a zero width space is no control character.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\x1fb", True),
        ("\x85", True),
        ("\t", True),
        ("062A", False),
        ("\xe9\xa0", False),
        ("\N{ZERO WIDTH SPACE}", False),
    ],
)
def test_has_control_character_tells_a_text_holding_one(*, text: str, expected: bool) -> None:
    assert has_control_character(text) is expected


def _target(absolute_number: int, *, letter: str) -> TargetSegment:
    return TargetSegment(
        season=1, seasonal_number=1, absolute_number=absolute_number, letter=letter, title="x"
    )


def test_targets_of_distinct_ids_hold_no_duplicate() -> None:
    assert (
        duplicate_targets([_target(1, letter="A"), _target(1, letter="B"), _target(2, letter="A")])
        == ()
    )


def test_every_duplicate_target_names_its_first_holder_letters_upper_cased() -> None:
    targets = [
        _target(62, letter="a"),
        _target(10, letter="A"),
        _target(62, letter="A"),
        _target(10, letter="A"),
        _target(62, letter="a"),
    ]
    assert duplicate_targets(targets) == (
        TargetDuplicate(index=2, first_index=0),
        TargetDuplicate(index=3, first_index=1),
        TargetDuplicate(index=4, first_index=0),
    )


def test_regex_with_date_alt_placeholder_is_rejected() -> None:
    # {date_alt} removed: a token using it fails at load time (unknown placeholder).
    with pytest.raises(MatchingConfigError, match="date_alt"):
        validate_config(MatcherConfig(tokens={"air": RegexDefinition(pattern="{date_alt}")}))


def test_token_reference_with_coverage_token_no_override_ok() -> None:
    """TokenReference on a coverage without an override: valid, no error."""
    rule = _rule(AllDefinition(operands=(TokenReference(name="title_hit"),)))
    validate_config(MatcherConfig(tokens={"title_hit": _COVERAGE}, rules=(rule,)))


# --- Task 6: graph validation (DAG, depth, RE2 compile-check) ---


def test_unknown_token_reference_raises_and_names_it() -> None:
    tokens: dict[str, TokenDefinition] = {
        "kt": AnyDefinition(operands=("keroro", "ghost")),
        "keroro": _KERORO,
    }
    with pytest.raises(UnknownTokenError, match="ghost"):
        validate_config(MatcherConfig(tokens=tokens))


def test_unknown_token_in_rule_raises() -> None:
    rule = _rule(AllDefinition(operands=("keroro", "ghost")))
    with pytest.raises(UnknownTokenError, match="ghost"):
        validate_config(MatcherConfig(tokens={"keroro": _KERORO}, rules=(rule,)))


def test_direct_cycle_is_detected_and_named() -> None:
    tokens = {"a": AnyDefinition(operands=("b",)), "b": AnyDefinition(operands=("a",))}
    with pytest.raises(CycleError) as excinfo:
        validate_config(MatcherConfig(tokens=tokens))
    message = str(excinfo.value)
    assert "a -> b -> a" in message or "b -> a -> b" in message


def test_self_cycle_is_detected() -> None:
    with pytest.raises(CycleError, match="loop"):
        validate_config(MatcherConfig(tokens={"loop": AnyDefinition(operands=("loop",))}))


def test_acyclic_composite_graph_validates() -> None:
    tokens: dict[str, TokenDefinition] = {
        "keroro": _KERORO,
        "titar": KeywordDefinition(phrase="titar"),
        "kt": AnyDefinition(operands=("keroro", "titar")),
        "deep": AllDefinition(operands=("kt", "keroro")),
        "not_deep": NotDefinition(operand="deep"),
    }
    rule = _rule(NotDefinition(operand=AnyDefinition(operands=("not_deep",))))
    validate_config(MatcherConfig(tokens=tokens, rules=(rule,)))


def test_regex_compile_check_rejects_bad_pattern() -> None:
    with pytest.raises(MatchingConfigError, match="not compilable"):
        validate_config(MatcherConfig(tokens={"bad": RegexDefinition(pattern="(unbalanced")}))


def test_regex_unknown_placeholder_rejected_at_load() -> None:
    with pytest.raises(MatchingConfigError, match="bogus"):
        validate_config(MatcherConfig(tokens={"bad": RegexDefinition(pattern="n {bogus}")}))


def test_regex_with_known_placeholders_validates() -> None:
    pattern = "n[°o]?\\s*0*{absolute_number}\\s*{letter}"
    validate_config(MatcherConfig(tokens={"seg": RegexDefinition(pattern=pattern)}))


def test_a_regex_without_the_flag_i_validates() -> None:
    video = RegexDefinition(pattern="\\.(avi|mkv)$", flags="")
    validate_config(MatcherConfig(tokens={"video": video}))


def test_depth_within_bound_validates() -> None:
    # Chain t2 -> t1 -> t0 (depth 3) with max_depth=3: OK.
    validate_config(MatcherConfig(tokens=_chain(3)), max_depth=3)


def test_depth_exceeded_raises() -> None:
    with pytest.raises(DepthExceededError, match="depth"):
        validate_config(MatcherConfig(tokens=_chain(3)), max_depth=2)


def test_default_max_depth_is_32() -> None:
    # A chain of 34 tokens exceeds the default 32.
    with pytest.raises(DepthExceededError):
        validate_config(MatcherConfig(tokens=_chain(34)))


def test_deep_chain_root_first_caught_by_dfs_guard() -> None:
    # Root-first order: _check_acyclic's DFS descends the whole chain, so the
    # len(stack)>=max_depth guard raises DepthExceededError before any RecursionError.
    tokens = dict(reversed(_chain(41).items()))
    with pytest.raises(DepthExceededError):
        validate_config(MatcherConfig(tokens=tokens))


def test_empty_config_validates() -> None:
    # Empty token table: _max_resolution_depth must return 0 (default), no error.
    validate_config(MatcherConfig())


def test_coverage_override_forward_reference_in_composite_validates() -> None:
    # Regression: a composite token referencing {token: cov, min: …} where cov is
    # defined AFTER must NOT be rejected (override validation deferred to the graph).
    combo = AnyDefinition(operands=(TokenReference(name="title_hit", min_coverage=0.4), "keroro"))
    tokens: dict[str, TokenDefinition] = {
        "combo": combo,
        "title_hit": _COVERAGE,
        "keroro": _KERORO,
    }
    validate_config(MatcherConfig(tokens=tokens))


# --- fragments: raw regex text substituted into regex tokens at parse time ---


def test_a_fragment_is_expanded_wherever_a_pattern_cites_it() -> None:
    pattern = expand_fragments(
        "{marker}\\d|\\b{marker}x{2,3}", fragments={"marker": "(?:n°|#)\\s*"}
    )
    assert pattern == "(?:n°|#)\\s*\\d|\\b(?:n°|#)\\s*x{2,3}"


def test_a_fragment_keeps_its_target_placeholders_for_per_target_interpolation() -> None:
    pattern = expand_fragments("n°{own}{letter}", fragments={"own": "0*{absolute_number}"})
    assert pattern == "n°0*{absolute_number}{letter}"


def test_fragments_of_one_level_named_apart_from_the_placeholders_hold_no_problem() -> None:
    fragments = {"marker": "#\\s*", "own": "{marker_text}0*{absolute_number}"}
    assert fragment_problems(fragments, file_path=_FILE) == ()


@pytest.mark.parametrize(
    "name", ["season", "seasonal_number", "absolute_number", "letter", "title"]
)
def test_a_fragment_named_like_a_target_placeholder_is_a_problem(name: str) -> None:
    assert fragment_problems({name: "x"}, file_path=_FILE) == (
        ConfigProblem(
            file_path=_FILE,
            key=f"fragments.{name}",
            message="collides with a target placeholder",
        ),
    )


def test_every_fragment_citing_a_fragment_is_a_problem() -> None:
    fragments = {"outer": "a{inner}{other}", "inner": "b", "other": "{inner}"}
    assert fragment_problems(fragments, file_path=_FILE) == (
        ConfigProblem(
            file_path=_FILE, key="fragments.outer", message="references fragment 'inner'"
        ),
        ConfigProblem(
            file_path=_FILE, key="fragments.outer", message="references fragment 'other'"
        ),
        ConfigProblem(
            file_path=_FILE, key="fragments.other", message="references fragment 'inner'"
        ),
    )


# --- vetoes: token names judged on every name of the file ---


def test_veto_naming_an_unknown_token_is_rejected() -> None:
    with pytest.raises(UnknownTokenError, match="veto references an unknown token: 'ghost'"):
        validate_config(MatcherConfig(tokens={"a": _KERORO}, vetoes=("ghost",)))


def test_duplicate_veto_is_rejected() -> None:
    with pytest.raises(MatchingConfigError, match="duplicate veto: 'a'"):
        validate_config(MatcherConfig(tokens={"a": _KERORO}, vetoes=("a", "a")))
