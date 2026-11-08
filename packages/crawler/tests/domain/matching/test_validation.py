import re

import pytest

from p2pwatch.domain.matching.config import (
    AllDefinition,
    AnyDefinition,
    AttributeBetweenDefinition,
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
    has_control_character,
    parse_condition,
    parse_matcher_config,
    parse_rule,
    validate_config,
)

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


def test_parse_leaf_token_definitions() -> None:
    config = parse_matcher_config(
        {
            "tokens": {
                "keroro": {"keyword": "keroro"},
                "teletoon": {"regex": "t[eé]l[eé]toon"},
                "video": {"regex": "\\.(avi|mkv)$", "flags": ""},
                "title_hit": {"coverage": "title", "min_coverage": 0.6, "min_similarity": 0.9},
                "small": {"attr_between": "size_mib", "min": 30, "max": 600},
            },
            "rules": [],
        }
    )
    assert config.tokens["keroro"] == KeywordDefinition(phrase="keroro")
    assert config.tokens["teletoon"] == RegexDefinition(pattern="t[eé]l[eé]toon", flags="i")
    assert config.tokens["video"] == RegexDefinition(pattern="\\.(avi|mkv)$", flags="")
    assert config.tokens["title_hit"] == CoverageDefinition(
        reference="title", min_coverage=0.6, min_similarity=0.9
    )
    assert config.tokens["small"] == AttributeBetweenDefinition(
        attr="size_mib", min_bound=30.0, max_bound=600.0
    )


def test_parse_composite_token_definition() -> None:
    assert parse_condition({"any": ["keroro", "titar"]}) == AnyDefinition(
        operands=("keroro", "titar")
    )


def test_parse_not_token_definition() -> None:
    assert parse_condition({"not": "keroro"}) == NotDefinition(operand="keroro")


def test_parse_rule_with_inline_token_reference_and_condition() -> None:
    rule = parse_rule(
        {
            "name": "numero_titre",
            "tier": "notify",
            "scope": "unattributed",
            "all": ["seg", {"token": "title_hit", "min_coverage": 0.5}],
        }
    )
    assert rule.name == "numero_titre"
    assert rule.tier is DecisionTier.NOTIFY
    assert rule.condition == AllDefinition(
        operands=("seg", TokenReference(name="title_hit", min_coverage=0.5))
    )


def test_parse_rule_with_nested_inline_condition() -> None:
    rule = parse_rule(
        {
            "name": "r",
            "tier": "catalog",
            "scope": "unattributed",
            "not": {"any": ["keroro", "titar"]},
        }
    )
    assert rule.condition == NotDefinition(operand=AnyDefinition(operands=("keroro", "titar")))


def test_unknown_tier_raises_and_names_it() -> None:
    with pytest.raises(MatchingConfigError, match="bogus"):
        parse_rule({"name": "r", "tier": "bogus", "scope": "unattributed", "any": ["keroro"]})


def test_parse_rule_reads_its_scope() -> None:
    rule = parse_rule({"name": "r", "tier": "notify", "scope": "episode", "any": ["keroro"]})
    assert rule.scope == "episode"


def test_rule_without_scope_raises_and_names_the_rule() -> None:
    # A matcher.yml from before scopes must fail at boot, not silently lose its fan-out.
    with pytest.raises(MatchingConfigError, match="rule 'numero_nu' without 'scope'"):
        parse_rule({"name": "numero_nu", "tier": "notify", "any": ["keroro"]})


def test_unknown_scope_raises_and_names_it() -> None:
    with pytest.raises(MatchingConfigError, match="unknown scope for rule 'r': 'target'"):
        parse_rule({"name": "r", "tier": "notify", "scope": "target", "any": ["keroro"]})


def test_attr_between_unknown_attr_raises_and_names_it() -> None:
    with pytest.raises(MatchingConfigError, match="codec"):
        parse_matcher_config({"tokens": {"c": {"attr_between": "codec", "min": 1}}, "rules": []})


def test_unknown_token_definition_shape_raises() -> None:
    with pytest.raises(MatchingConfigError, match="unknown token shape"):
        parse_matcher_config({"tokens": {"x": {"frobnicate": "y"}}, "rules": []})


def test_token_definition_with_multiple_keys_raises() -> None:
    with pytest.raises(MatchingConfigError, match="exactly one type-key"):
        parse_matcher_config({"tokens": {"x": {"keyword": "a", "regex": "b"}}, "rules": []})


def test_override_on_non_coverage_token_raises() -> None:
    rule = _rule(AllDefinition(operands=(TokenReference(name="kw", min_coverage=0.5),)))
    with pytest.raises(MatchingConfigError, match="kw"):
        validate_config(MatcherConfig(tokens={"kw": _KERORO}, rules=(rule,)))


def test_rule_without_condition_key_raises() -> None:
    with pytest.raises(MatchingConfigError, match="condition"):
        parse_rule({"name": "r", "tier": "catalog", "scope": "unattributed"})


def test_rule_with_two_condition_keys_raises() -> None:
    with pytest.raises(MatchingConfigError, match="exactly one condition"):
        parse_rule(
            {
                "name": "r",
                "tier": "catalog",
                "scope": "unattributed",
                "all": ["keroro"],
                "any": ["keroro"],
            }
        )


def test_rule_with_empty_all_is_rejected() -> None:
    # config-validation#0: AllMatcher([]).matches() == all([]) == True → a rule 'all: []'
    # would unconditionally match EVERY file (here in tier=download → auto-download).
    # EBNF §8.3 requires >=1 operand; fail-fast must reject it at load time.
    with pytest.raises(MatchingConfigError, match="at least one operand"):
        parse_rule({"name": "pwn", "tier": "download", "scope": "unattributed", "all": []})


def test_rule_with_empty_any_is_rejected() -> None:
    # Same fail-fast gap for 'any: []' (EBNF §8.3: >=1 operand), degenerate config.
    with pytest.raises(MatchingConfigError, match="at least one operand"):
        parse_rule({"name": "pwn", "tier": "download", "scope": "unattributed", "any": []})


def test_coverage_min_out_of_unit_range_is_rejected() -> None:
    # config-validation#2: min_coverage/min_similarity are logical fractions [0, 1].
    # 'min_coverage: 5.0' (typo for 0.5) would make the rule silently INERT (coverage() <= 1
    # always false → never matches) with no signal at load time → fail-fast §8.4.
    with pytest.raises(MatchingConfigError, match=r"\[0, 1\]"):
        parse_matcher_config(
            {"tokens": {"t": {"coverage": "title", "min_coverage": 5.0}}, "rules": []}
        )


def test_coverage_fuzz_out_of_unit_range_is_rejected() -> None:
    # 'min_similarity: 99' (typo for 0.99) → ratio/100 >= 99 always false → mute rule.
    with pytest.raises(MatchingConfigError, match=r"\[0, 1\]"):
        parse_matcher_config(
            {
                "tokens": {"t": {"coverage": "title", "min_coverage": 0.5, "min_similarity": 99}},
                "rules": [],
            }
        )


def test_coverage_override_min_out_of_unit_range_is_rejected() -> None:
    # Same bound for a min_coverage/min_similarity override on a TokenReference (coverage).
    with pytest.raises(MatchingConfigError, match=r"\[0, 1\]"):
        parse_rule(
            {
                "name": "r",
                "tier": "catalog",
                "scope": "unattributed",
                "all": [{"token": "cov", "min_coverage": 5.0}],
            }
        )


@pytest.mark.parametrize(
    ("coverage_token", "old_key", "new_key"),
    [
        ({"coverage": "title", "min": 0.6}, "min", "min_coverage"),
        ({"coverage": "title", "min_coverage": 0.6, "fuzz": 0.9}, "fuzz", "min_similarity"),
    ],
)
def test_a_coverage_tokens_4x_key_is_refused_with_its_new_name(
    *, coverage_token: dict[str, object], old_key: str, new_key: str
) -> None:
    message = (
        f"token 'title_hit': key '{old_key}' was renamed '{new_key}', rename it in matcher.yml"
    )
    with pytest.raises(MatchingConfigError, match=re.escape(message)):
        parse_matcher_config({"tokens": {"title_hit": coverage_token}, "rules": []})


@pytest.mark.parametrize(
    ("old_key", "new_key"), [("min", "min_coverage"), ("fuzz", "min_similarity")]
)
def test_a_token_references_4x_override_is_refused_with_its_new_name(
    *, old_key: str, new_key: str
) -> None:
    message = (
        f"operand {{token: 'cov'}}: key '{old_key}' was renamed '{new_key}', "
        "rename it in matcher.yml"
    )
    with pytest.raises(MatchingConfigError, match=re.escape(message)):
        parse_rule(
            {
                "name": "r",
                "tier": "catalog",
                "scope": "unattributed",
                "all": [{"token": "cov", old_key: 0.5}],
            }
        )


@pytest.mark.parametrize(
    ("old_attr", "new_attr"), [("size_mb", "size_mib"), ("duration_sec", "duration_seconds")]
)
def test_a_4x_attr_between_attribute_is_refused_with_its_new_name(
    *, old_attr: str, new_attr: str
) -> None:
    message = f"attr_between '{old_attr}' was renamed '{new_attr}', rename it in matcher.yml"
    with pytest.raises(MatchingConfigError, match=re.escape(message)):
        parse_matcher_config({"tokens": {"t": {"attr_between": old_attr, "min": 1}}, "rules": []})


def test_attr_between_min_greater_than_max_is_rejected() -> None:
    # config-validation#1: {attr_between: size_mib, min: 600, max: 30} = EMPTY range → the rule is
    # mute forever (input error). OPEN bounds (min only / max only) stay valid: it is
    # deliberate and tested; only min > max is rejected.
    with pytest.raises(MatchingConfigError, match="min.*>.*max"):
        parse_matcher_config(
            {"tokens": {"sz": {"attr_between": "size_mib", "min": 600, "max": 30}}, "rules": []}
        )


def test_token_reference_missing_name_raises() -> None:
    with pytest.raises(MatchingConfigError, match="token"):
        parse_rule(
            {
                "name": "r",
                "tier": "catalog",
                "scope": "unattributed",
                "all": [{"min_coverage": 0.5}],
            }
        )


def test_operand_wrong_type_raises() -> None:
    with pytest.raises(MatchingConfigError, match="operand"):
        parse_rule({"name": "r", "tier": "catalog", "scope": "unattributed", "all": [123]})


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


# --- Branch-coverage leftovers ---


def test_token_definition_non_mapping_raises() -> None:
    """_require_mapping raises MatchingConfigError if the token definition is not a mapping."""
    with pytest.raises(MatchingConfigError, match="mapping"):
        parse_matcher_config({"tokens": {"x": "not-a-dict"}, "rules": []})


def test_composite_token_definition_multiple_condition_keys_raises() -> None:
    """_parse_condition raises if a composite token contains 2+ condition keys."""
    with pytest.raises(MatchingConfigError, match="exactly one condition"):
        parse_matcher_config({"tokens": {"x": {"all": ["a"], "any": ["b"]}}, "rules": []})


def test_all_body_non_list_raises() -> None:
    """parse_condition raises if the body of 'all' is not a list."""
    with pytest.raises(MatchingConfigError, match="list"):
        parse_rule({"name": "r", "tier": "catalog", "scope": "unattributed", "all": "keroro"})


def test_coverage_token_missing_min_raises() -> None:
    """_parse_token_definition raises if a coverage does not declare 'min_coverage'."""
    with pytest.raises(MatchingConfigError, match="'min_coverage'"):
        parse_matcher_config({"tokens": {"t": {"coverage": "title"}}, "rules": []})


def test_rule_without_name_raises() -> None:
    """parse_rule raises if a rule has no 'name'."""
    with pytest.raises(MatchingConfigError, match="name"):
        parse_rule({"tier": "catalog", "scope": "unattributed", "any": ["keroro"]})


@pytest.mark.parametrize("name", ["a\tb", "\x1f", "\x85", "\x7f"])
def test_a_rule_name_holding_a_control_character_is_refused_and_named(name: str) -> None:
    with pytest.raises(MatchingConfigError) as raised:
        parse_rule({"name": name, "tier": "catalog", "scope": "unattributed", "any": ["keroro"]})
    assert str(raised.value) == f"rule name {name!r} holds a control character"


def test_a_rule_name_beyond_ascii_that_is_no_control_character_is_accepted() -> None:
    rule = parse_rule(
        {"name": "\xe9\xa0", "tier": "catalog", "scope": "unattributed", "any": ["keroro"]}
    )
    assert rule.name == "\xe9\xa0"


def test_rules_non_list_raises() -> None:
    """parse_matcher_config raises if 'rules' is not a list."""
    with pytest.raises(MatchingConfigError, match="rules"):
        parse_matcher_config({"tokens": {}, "rules": "not-a-list"})


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


def test_the_4x_segment_placeholder_is_refused_with_its_new_name() -> None:
    message = (
        "token 'seg': placeholder '{segment}' was renamed '{letter}', rename it in matcher.yml"
    )
    with pytest.raises(MatchingConfigError, match=re.escape(message)):
        parse_matcher_config({"tokens": {"seg": {"regex": "n°{absolute_number}{segment}"}}})


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


def test_fragment_is_expanded_into_regex_tokens_at_parse_time() -> None:
    config = parse_matcher_config(
        {
            "fragments": {"marker": "(?:n°|#)\\s*"},
            "tokens": {"explicit": {"regex": "{marker}\\d|\\b{marker}x{2,3}"}},
        }
    )
    assert config.tokens["explicit"] == RegexDefinition(
        pattern="(?:n°|#)\\s*\\d|\\b(?:n°|#)\\s*x{2,3}"
    )


def test_fragment_keeps_its_target_placeholders_for_per_target_interpolation() -> None:
    config = parse_matcher_config(
        {"fragments": {"own": "0*{absolute_number}"}, "tokens": {"id": {"regex": "n°{own}"}}}
    )
    assert config.tokens["id"] == RegexDefinition(pattern="n°0*{absolute_number}")


@pytest.mark.parametrize(
    "name", ["season", "seasonal_number", "absolute_number", "letter", "title"]
)
def test_fragment_named_like_a_target_placeholder_is_rejected(name: str) -> None:
    with pytest.raises(
        MatchingConfigError, match=f"fragment {name!r} collides with a target placeholder"
    ):
        parse_matcher_config({"fragments": {name: "x"}})


def test_fragment_referencing_another_fragment_is_rejected() -> None:
    with pytest.raises(MatchingConfigError, match="fragment 'outer' references fragment 'inner'"):
        parse_matcher_config(
            {
                "fragments": {"outer": "a{inner}", "inner": "b"},
                "tokens": {"t": {"regex": "{outer}"}},
            }
        )


def test_placeholder_that_is_neither_fragment_nor_target_field_is_rejected() -> None:
    with pytest.raises(MatchingConfigError, match="token 't': invalid interpolation"):
        parse_matcher_config({"fragments": {"known": "x"}, "tokens": {"t": {"regex": "{unknown}"}}})


def test_fragments_section_must_be_a_mapping() -> None:
    with pytest.raises(MatchingConfigError, match="'fragments' section"):
        parse_matcher_config({"fragments": ["x"]})


# --- vetoes: token names judged on every name of the file ---


def test_parse_vetoes_keeps_their_order() -> None:
    config = parse_matcher_config(
        {"tokens": {"a": {"keyword": "a"}, "b": {"keyword": "b"}}, "vetoes": ["b", "a"]}
    )
    assert config.vetoes == ("b", "a")


def test_vetoes_are_optional() -> None:
    assert parse_matcher_config({"tokens": {"a": {"keyword": "a"}}}).vetoes == ()


def test_veto_naming_an_unknown_token_is_rejected() -> None:
    with pytest.raises(UnknownTokenError, match="veto references an unknown token: 'ghost'"):
        validate_config(MatcherConfig(tokens={"a": _KERORO}, vetoes=("ghost",)))


def test_duplicate_veto_is_rejected() -> None:
    with pytest.raises(MatchingConfigError, match="duplicate veto: 'a'"):
        validate_config(MatcherConfig(tokens={"a": _KERORO}, vetoes=("a", "a")))


def test_vetoes_section_must_be_a_list() -> None:
    with pytest.raises(MatchingConfigError, match="'vetoes' section: list expected"):
        parse_matcher_config({"tokens": {"a": {"keyword": "a"}}, "vetoes": "a"})


@pytest.mark.parametrize(
    ("token", "message"),
    [
        (
            {"coverage": "title", "min_coverage": "abc"},
            "token 't': key 'min_coverage': number expected, got 'abc'",
        ),
        (
            {"coverage": "title", "min_coverage": 0.5, "min_similarity": [1]},
            "token 't': key 'min_similarity': number expected, got [1]",
        ),
        (
            {"attr_between": "size_mib", "min": "big"},
            "token 't': key 'min': number expected, got 'big'",
        ),
        ({"attr_between": "size_mib", "max": {}}, "token 't': key 'max': number expected, got {}"),
    ],
    ids=["min_coverage", "min_similarity", "min", "max"],
)
def test_a_token_number_that_is_no_number_raises_and_names_its_key(
    *, token: dict[str, object], message: str
) -> None:
    with pytest.raises(MatchingConfigError) as raised:
        parse_matcher_config({"tokens": {"t": token}, "rules": []})
    assert str(raised.value) == message


@pytest.mark.parametrize("override_key", ["min_coverage", "min_similarity"])
def test_an_override_that_is_no_number_raises_and_names_it(override_key: str) -> None:
    rule = {
        "name": "r",
        "tier": "catalog",
        "scope": "unattributed",
        "all": [{"token": "cov", override_key: "x"}],
    }
    with pytest.raises(MatchingConfigError) as raised:
        parse_matcher_config(
            {"tokens": {"cov": {"coverage": "title", "min_coverage": 0.5}}, "rules": [rule]}
        )
    assert str(raised.value) == f"'{override_key}' override of 'cov': number expected, got 'x'"
