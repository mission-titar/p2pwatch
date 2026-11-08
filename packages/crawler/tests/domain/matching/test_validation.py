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
    TargetDuplicate,
    cross_value_problems,
    duplicate_targets,
    expand_fragments,
    fragment_problems,
    has_control_character,
)

_FILE = PurePath("/srv/matcher.yml")
_KERORO = KeywordDefinition(phrase="keroro")
_COVERAGE = CoverageDefinition(reference="title", min_coverage=0.5)
_KERORO_ONLY = AllDefinition(operands=("keroro",))
_UNKNOWN = "references an unknown token"
_OVERRIDE = "can only override a coverage token"
_PLACEHOLDER = "cites a placeholder neither a fragment nor a target field"
_NOT_COMPILABLE = "does not compile as a regex"


def _rule(condition: Condition) -> Rule:
    return Rule(name="r", tier=DecisionTier.CATALOG, scope="unattributed", condition=condition)


def _chain(length: int) -> dict[str, TokenDefinition]:
    """``t0`` a keyword, each ``t<i>`` up to ``t<length - 1>`` citing ``t<i - 1>``."""
    chain: dict[str, TokenDefinition] = {"t0": KeywordDefinition(phrase="x")}
    for index in range(1, length):
        chain[f"t{index}"] = AnyDefinition(operands=(f"t{index - 1}",))
    return chain


def _problems(config: MatcherConfig, *, max_depth: int | None = None) -> list[tuple[str, str]]:
    """The key and message of each problem of ``config``, all of them in ``_FILE``."""
    if max_depth is None:
        problems = cross_value_problems(config, file_path=_FILE)
    else:
        problems = cross_value_problems(config, file_path=_FILE, max_depth=max_depth)
    assert {problem.file_path for problem in problems} <= {_FILE}
    return [(str(problem.key), problem.message) for problem in problems]


def test_an_override_on_a_token_that_is_not_a_coverage_one_is_a_problem() -> None:
    rule = _rule(AllDefinition(operands=(TokenReference(name="kw", min_coverage=0.5),)))
    config = MatcherConfig(tokens={"kw": _KERORO}, rules=(rule,))
    assert _problems(config) == [("rules[0].all[0].min_coverage", _OVERRIDE)]


def test_each_override_of_a_token_that_is_not_a_coverage_one_is_a_problem() -> None:
    reference = TokenReference(name="kw", min_coverage=0.5, min_similarity=0.8)
    tokens: dict[str, TokenDefinition] = {"kw": _KERORO, "t": NotDefinition(operand=reference)}
    assert _problems(MatcherConfig(tokens=tokens)) == [
        ("tokens.t.not.min_coverage", _OVERRIDE),
        ("tokens.t.not.min_similarity", _OVERRIDE),
    ]


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


def test_a_regex_citing_the_removed_date_alt_placeholder_is_a_problem() -> None:
    config = MatcherConfig(tokens={"air": RegexDefinition(pattern="{date_alt}")})
    assert _problems(config) == [("tokens.air.regex", _PLACEHOLDER)]


def test_token_reference_with_coverage_token_no_override_ok() -> None:
    rule = _rule(AllDefinition(operands=(TokenReference(name="title_hit"),)))
    assert _problems(MatcherConfig(tokens={"title_hit": _COVERAGE}, rules=(rule,))) == []


def test_a_reference_to_an_unknown_token_in_a_token_is_a_problem_at_its_place() -> None:
    tokens: dict[str, TokenDefinition] = {
        "kt": AnyDefinition(operands=("keroro", "ghost")),
        "keroro": _KERORO,
    }
    assert _problems(MatcherConfig(tokens=tokens)) == [("tokens.kt.any[1]", _UNKNOWN)]


def test_a_reference_to_an_unknown_token_in_a_rule_is_a_problem_at_its_place() -> None:
    inline = AnyDefinition(operands=(TokenReference(name="ghost", min_coverage=0.5),))
    rule = _rule(AllDefinition(operands=("keroro", inline)))
    config = MatcherConfig(tokens={"keroro": _KERORO}, rules=(_rule(_KERORO_ONLY), rule))
    assert _problems(config) == [("rules[1].all[1].any[0].token", _UNKNOWN)]


def test_a_direct_cycle_is_a_problem_naming_it() -> None:
    tokens = {"a": AnyDefinition(operands=("b",)), "b": AnyDefinition(operands=("a",))}
    assert _problems(MatcherConfig(tokens=tokens)) == [
        ("tokens.b.any[0]", "closes the reference cycle a -> b -> a")
    ]


def test_a_self_cycle_is_a_problem() -> None:
    config = MatcherConfig(tokens={"loop": NotDefinition(operand=TokenReference(name="loop"))})
    assert _problems(config) == [
        ("tokens.loop.not.token", "closes the reference cycle loop -> loop")
    ]


def test_every_cycle_is_one_problem_and_the_depth_waits_for_none() -> None:
    tokens: dict[str, TokenDefinition] = {
        **_chain(34),
        "a": AnyDefinition(operands=("b", "c")),
        "b": AnyDefinition(operands=("a",)),
        "c": AnyDefinition(operands=("a",)),
        "before_loop": AnyDefinition(operands=("loop",)),
        "loop": AnyDefinition(operands=("loop",)),
        "after_loop": AnyDefinition(operands=("loop",)),
    }
    assert _problems(MatcherConfig(tokens=tokens)) == [
        ("tokens.b.any[0]", "closes the reference cycle a -> b -> a"),
        ("tokens.c.any[0]", "closes the reference cycle a -> c -> a"),
        ("tokens.loop.any[0]", "closes the reference cycle loop -> loop"),
    ]


def test_acyclic_composite_graph_validates() -> None:
    tokens: dict[str, TokenDefinition] = {
        "keroro": _KERORO,
        "titar": KeywordDefinition(phrase="titar"),
        "kt": AnyDefinition(operands=("keroro", "titar")),
        "deep": AllDefinition(operands=("kt", "keroro")),
        "not_deep": NotDefinition(operand="deep"),
    }
    rule = _rule(NotDefinition(operand=AnyDefinition(operands=("not_deep",))))
    assert _problems(MatcherConfig(tokens=tokens, rules=(rule,))) == []


def test_a_regex_that_does_not_compile_is_a_problem() -> None:
    config = MatcherConfig(tokens={"bad": RegexDefinition(pattern="(unbalanced")})
    assert _problems(config) == [("tokens.bad.regex", _NOT_COMPILABLE)]


def test_a_regex_citing_an_unknown_placeholder_is_a_problem() -> None:
    config = MatcherConfig(tokens={"bad": RegexDefinition(pattern="n {bogus}")})
    assert _problems(config) == [("tokens.bad.regex", _PLACEHOLDER)]


def test_regex_with_known_placeholders_validates() -> None:
    pattern = "n[°o]?\\s*0*{absolute_number}\\s*{letter}"
    assert _problems(MatcherConfig(tokens={"seg": RegexDefinition(pattern=pattern)})) == []


def test_a_regex_without_the_flag_i_validates() -> None:
    video = RegexDefinition(pattern="\\.(avi|mkv)$", flags="")
    assert _problems(MatcherConfig(tokens={"video": video})) == []


def test_depth_within_bound_validates() -> None:
    assert _problems(MatcherConfig(tokens=_chain(3)), max_depth=3) == []


def test_a_depth_past_the_bound_is_a_problem_at_the_deepest_token() -> None:
    assert _problems(MatcherConfig(tokens=_chain(3)), max_depth=2) == [
        ("tokens.t2", "resolves through 3 levels of tokens, past the bound 2")
    ]


def test_default_max_depth_is_32() -> None:
    assert _problems(MatcherConfig(tokens=_chain(34))) == [
        ("tokens.t33", "resolves through 34 levels of tokens, past the bound 32")
    ]


def test_a_chain_past_the_interpreters_recursion_limit_is_walked_root_first() -> None:
    tokens = dict(reversed(_chain(5000).items()))
    assert _problems(MatcherConfig(tokens=tokens)) == [
        ("tokens.t4999", "resolves through 5000 levels of tokens, past the bound 32")
    ]


def test_empty_config_validates() -> None:
    assert _problems(MatcherConfig()) == []


def test_coverage_override_forward_reference_in_composite_validates() -> None:
    combo = AnyDefinition(operands=(TokenReference(name="title_hit", min_coverage=0.4), "keroro"))
    tokens: dict[str, TokenDefinition] = {
        "combo": combo,
        "title_hit": _COVERAGE,
        "keroro": _KERORO,
    }
    assert _problems(MatcherConfig(tokens=tokens)) == []


def test_every_problem_across_values_is_listed() -> None:
    rule = _rule(AllDefinition(operands=("ghost", TokenReference(name="kw", min_similarity=0.8))))
    tokens: dict[str, TokenDefinition] = {
        "kw": _KERORO,
        "kt": NotDefinition(operand="phantom"),
        "a": AnyDefinition(operands=("a",)),
        "bad": RegexDefinition(pattern="(unbalanced"),
        "air": RegexDefinition(pattern="{date_alt}"),
    }
    config = MatcherConfig(tokens=tokens, rules=(rule,), vetoes=("kw", "spectre", "kw"))
    assert _problems(config) == [
        ("tokens.kt.not", _UNKNOWN),
        ("rules[0].all[0]", _UNKNOWN),
        ("rules[0].all[1].min_similarity", _OVERRIDE),
        ("vetoes[1]", _UNKNOWN),
        ("vetoes[2]", "same token as vetoes[0]"),
        ("tokens.a.any[0]", "closes the reference cycle a -> a"),
        ("tokens.bad.regex", _NOT_COMPILABLE),
        ("tokens.air.regex", _PLACEHOLDER),
    ]


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


def test_a_veto_naming_an_unknown_token_is_a_problem() -> None:
    config = MatcherConfig(tokens={"a": _KERORO}, vetoes=("a", "ghost"))
    assert _problems(config) == [("vetoes[1]", _UNKNOWN)]


def test_each_duplicate_veto_names_its_first_place() -> None:
    config = MatcherConfig(tokens={"a": _KERORO}, vetoes=("a", "a", "a"))
    assert _problems(config) == [
        ("vetoes[1]", "same token as vetoes[0]"),
        ("vetoes[2]", "same token as vetoes[0]"),
    ]
