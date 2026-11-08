from pathlib import PurePath
from typing import Any, get_args

import pytest

from p2pwatch.adapters.driven.config.matcher_config_schema import matcher_config_from_document
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.config import (
    AllDefinition,
    AnyDefinition,
    AttributeBetweenDefinition,
    CoverageDefinition,
    KeywordDefinition,
    MatcherConfig,
    NotDefinition,
    RegexDefinition,
    Rule,
    Scope,
    TokenReference,
)
from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.matchers import READERS_BY_ATTR

_FILE = PurePath("/srv/matcher.yml")


def _problems(document: dict[str, Any]) -> list[tuple[str | None, str]]:
    """The key and message of each problem of ``document``, all of them in ``_FILE``."""
    with pytest.raises(InvalidConfigError) as raised:
        matcher_config_from_document(document, file_path=_FILE)
    assert {problem.file_path for problem in raised.value.problems} == {_FILE}
    return [(problem.key, problem.message) for problem in raised.value.problems]


def _token_problems(token: object) -> list[tuple[str | None, str]]:
    return _problems({"tokens": {"t": token}})


def test_a_document_gives_its_matcher_config() -> None:
    document = {
        "tokens": {"titar": {"keyword": "mission titar"}, "keroro": {"keyword": "keroro"}},
        "rules": [{"name": "r", "tier": "notify", "scope": "episode", "any": ["titar"]}],
        "vetoes": ["titar", "keroro"],
    }
    rule = Rule(
        name="r",
        tier=DecisionTier.NOTIFY,
        scope="episode",
        condition=AnyDefinition(operands=("titar",)),
    )
    assert matcher_config_from_document(document, file_path=_FILE) == MatcherConfig(
        tokens={
            "titar": KeywordDefinition(phrase="mission titar"),
            "keroro": KeywordDefinition(phrase="keroro"),
        },
        rules=(rule,),
        vetoes=("titar", "keroro"),
    )


def test_a_regex_holds_the_fragments_it_cites() -> None:
    document = {
        "fragments": {"marker": "(?:n°|#)\\s*"},
        "tokens": {"own_id": {"regex": "{marker}0*{absolute_number}"}},
    }
    config = matcher_config_from_document(document, file_path=_FILE)
    assert config.tokens["own_id"] == RegexDefinition(pattern="(?:n°|#)\\s*0*{absolute_number}")


def test_every_problem_of_the_fragments_is_listed() -> None:
    document = {"fragments": {"title": "x", "outer": "a{inner}", "inner": "b"}}
    assert _problems(document) == [
        ("fragments.title", "collides with a target placeholder"),
        ("fragments.outer", "references fragment 'inner'"),
    ]


def test_a_placeholder_neither_fragment_nor_target_field_is_refused() -> None:
    document = {"fragments": {"known": "x"}, "tokens": {"t": {"regex": "{unknown}"}}}
    assert _problems(document) == [
        ("tokens.t.regex", "cites a placeholder neither a fragment nor a target field")
    ]


def test_each_token_shape_gives_its_definition() -> None:
    tokens = {
        "keroro": {"keyword": "keroro"},
        "teletoon": {"regex": "t[eé]l[eé]toon"},
        "video": {"regex": "\\.(avi|mkv)$", "flags": ""},
        "title_hit": {"coverage": "title", "min_coverage": 0.6},
        "close_title": {"coverage": "title", "min_coverage": 0.6, "min_similarity": 0.9},
        "small": {"attr_between": "size_mib", "min": 30, "max": 600},
        "long": {"attr_between": "duration_seconds", "min": 600},
        "either": {"any": ["keroro", "teletoon"]},
    }
    config = matcher_config_from_document({"tokens": tokens}, file_path=_FILE)
    assert config.tokens == {
        "keroro": KeywordDefinition(phrase="keroro"),
        "teletoon": RegexDefinition(pattern="t[eé]l[eé]toon", flags="i"),
        "video": RegexDefinition(pattern="\\.(avi|mkv)$", flags=""),
        "title_hit": CoverageDefinition(reference="title", min_coverage=0.6, min_similarity=0.85),
        "close_title": CoverageDefinition(reference="title", min_coverage=0.6, min_similarity=0.9),
        "small": AttributeBetweenDefinition(attr="size_mib", min_bound=30.0, max_bound=600.0),
        "long": AttributeBetweenDefinition(attr="duration_seconds", min_bound=600.0),
        "either": AnyDefinition(operands=("keroro", "teletoon")),
    }


def test_every_problem_of_the_fragments_and_tokens_is_listed() -> None:
    document = {
        "fragments": {"marker": 3},
        "tokens": {"a": {"keyword": 62}, "b": {"regex": "x", "flagz": "i"}},
        "rule": [],
    }
    assert _problems(document) == [
        ("fragments.marker", "Input should be a valid string"),
        ("tokens.a.keyword", "Input should be a valid string"),
        ("tokens.b.flagz", "Extra inputs are not permitted"),
        ("rule", "Extra inputs are not permitted"),
    ]


@pytest.mark.parametrize(
    ("document", "key", "message"),
    [
        ({"fragments": ["x"]}, "fragments", "Input should be a valid dictionary"),
        ({"tokens": ["x"]}, "tokens", "Input should be a valid dictionary"),
        ({"tokens": {"t": "keroro"}}, "tokens.t", "Input should be a valid dictionary"),
        ({"rules": {}}, "rules", "Input should be a valid list"),
        ({"vetoes": "a"}, "vetoes", "Input should be a valid list"),
        ({"vetoes": [3]}, "vetoes[0]", "Input should be a valid string"),
    ],
    ids=["fragments", "tokens", "token", "rules", "vetoes", "veto"],
)
def test_a_section_of_the_wrong_type_is_refused(
    *, document: dict[str, Any], key: str, message: str
) -> None:
    assert _problems(document) == [(key, message)]


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ({"frobnicate": "y", "other": 1}, "unknown token shape: keys ['frobnicate', 'other']"),
        (
            {"regex": "b", "keyword": "a"},
            "a leaf token has exactly one type-key, got ['keyword', 'regex']",
        ),
    ],
    ids=["none", "two"],
)
def test_a_token_of_no_shape_or_two_is_refused_naming_its_keys(
    *, token: dict[str, Any], message: str
) -> None:
    assert _token_problems(token) == [("tokens.t", message)]


def test_a_token_of_no_shape_is_listed_beside_the_other_problems() -> None:
    document = {"tokens": {"a": {"keyword": "x", "regex": "y"}, "b": {"keyword": 3}}}
    assert _problems(document) == [
        ("tokens.a", "a leaf token has exactly one type-key, got ['keyword', 'regex']"),
        ("tokens.b.keyword", "Input should be a valid string"),
    ]


@pytest.mark.parametrize(
    ("token", "key", "message"),
    [
        ({"keyword": "a", "flags": "i"}, "tokens.t.flags", "Extra inputs are not permitted"),
        ({"regex": 3}, "tokens.t.regex", "Input should be a valid string"),
        ({"regex": "x", "flags": True}, "tokens.t.flags", "Input should be a valid string"),
        (
            {"coverage": 1, "min_coverage": 0.5},
            "tokens.t.coverage",
            "Input should be a valid string",
        ),
        ({"coverage": "title"}, "tokens.t.min_coverage", "Field required"),
        (
            {"coverage": "title", "min_coverage": "0.6"},
            "tokens.t.min_coverage",
            "Input should be a valid number",
        ),
        (
            {"coverage": "title", "min_coverage": 5.0},
            "tokens.t.min_coverage",
            "Input should be less than or equal to 1",
        ),
        (
            {"coverage": "title", "min_coverage": -0.1},
            "tokens.t.min_coverage",
            "Input should be greater than or equal to 0",
        ),
        (
            {"coverage": "title", "min_coverage": 0.5, "min_similarity": 99},
            "tokens.t.min_similarity",
            "Input should be less than or equal to 1",
        ),
        (
            {"attr_between": "codec", "min": 1},
            "tokens.t.attr_between",
            "Input should be 'size_mib', 'duration_seconds' or 'bitrate_kbps'",
        ),
        (
            {"attr_between": "size_mib", "min": "big"},
            "tokens.t.min",
            "Input should be a valid number",
        ),
        (
            {"attr_between": "size_mib", "max": float("inf")},
            "tokens.t.max",
            "Input should be a finite number",
        ),
    ],
)
def test_a_wrong_leaf_value_is_refused_by_its_key(
    *, token: dict[str, Any], key: str, message: str
) -> None:
    assert _token_problems(token) == [(key, message)]


# The refusal of an unknown attribute lists the accepted ones: together, exactly the engine's.
@pytest.mark.parametrize("attribute", sorted(READERS_BY_ATTR))
def test_every_attribute_the_engine_reads_is_accepted(attribute: str) -> None:
    token = {"attr_between": attribute, "max": 1}
    config = matcher_config_from_document({"tokens": {"t": token}}, file_path=_FILE)
    assert config.tokens["t"] == AttributeBetweenDefinition(attr=attribute, max_bound=1.0)


def test_an_empty_size_range_is_refused() -> None:
    token = {"attr_between": "size_mib", "min": 600, "max": 30}
    assert _token_problems(token) == [("tokens.t", "'min' is above 'max', an empty range")]


def test_a_range_of_one_value_is_accepted() -> None:
    token = {"attr_between": "size_mib", "min": 30, "max": 30}
    config = matcher_config_from_document({"tokens": {"t": token}}, file_path=_FILE)
    assert config.tokens["t"] == AttributeBetweenDefinition(
        attr="size_mib", min_bound=30.0, max_bound=30.0
    )


@pytest.mark.parametrize(
    ("token", "key", "new_key"),
    [
        ({"coverage": "title", "min": 0.6}, "min", "min_coverage"),
        ({"coverage": "title", "min_coverage": 0.6, "fuzz": 0.9}, "fuzz", "min_similarity"),
    ],
)
def test_a_coverage_tokens_4x_key_is_one_problem_naming_its_new_name(
    *, token: dict[str, Any], key: str, new_key: str
) -> None:
    message = f"was renamed '{new_key}', rename it in matcher.yml"
    assert _token_problems(token) == [(f"tokens.t.{key}", message)]


@pytest.mark.parametrize(
    ("old_attribute", "new_attribute"),
    [("size_mb", "size_mib"), ("duration_sec", "duration_seconds")],
)
def test_a_4x_attribute_is_refused_naming_its_new_name(
    *, old_attribute: str, new_attribute: str
) -> None:
    message = f"'{old_attribute}' was renamed '{new_attribute}', rename it in matcher.yml"
    token = {"attr_between": old_attribute, "min": 1}
    assert _token_problems(token) == [("tokens.t.attr_between", message)]


_SEGMENT_RENAMED = "placeholder '{segment}' was renamed '{letter}', rename it in matcher.yml"


def test_the_4x_segment_placeholder_is_refused_in_a_regex_and_a_fragment() -> None:
    document = {
        "fragments": {"letter_mark": "\\s*{segment}"},
        "tokens": {"seg": {"regex": "n°{absolute_number}{segment}"}},
    }
    assert _problems(document) == [
        ("fragments.letter_mark", _SEGMENT_RENAMED),
        ("tokens.seg.regex", _SEGMENT_RENAMED),
    ]


def test_every_problem_across_values_is_listed_once_the_shape_holds() -> None:
    document = {
        "tokens": {"a": {"keyword": "a"}, "t": {"any": ["a", "ghost"]}},
        "rules": [_rule(all=[{"token": "a", "min_coverage": 0.5}])],
        "vetoes": ["t", "t"],
    }
    assert _problems(document) == [
        ("tokens.t.any[1]", "references an unknown token"),
        ("rules[0].all[0].min_coverage", "can only override a coverage token"),
        ("vetoes[1]", "same token as vetoes[0]"),
    ]


def _rule(**keys: object) -> dict[str, object]:
    return {"name": "r", "tier": "catalog", "scope": "unattributed", **keys}


def _rule_problems(rule: object) -> list[tuple[str | None, str]]:
    return _problems({"tokens": {"a": {"keyword": "a"}}, "rules": [rule]})


@pytest.mark.parametrize("tier", list(DecisionTier))
def test_every_tier_is_accepted(tier: DecisionTier) -> None:
    document = {"tokens": {"a": {"keyword": "a"}}, "rules": [_rule(tier=str(tier), any=["a"])]}
    [rule] = matcher_config_from_document(document, file_path=_FILE).rules
    assert rule.tier is tier


@pytest.mark.parametrize("scope", get_args(Scope.__value__))
def test_every_scope_is_accepted(scope: Scope) -> None:
    document = {"tokens": {"a": {"keyword": "a"}}, "rules": [_rule(scope=scope, any=["a"])]}
    [rule] = matcher_config_from_document(document, file_path=_FILE).rules
    assert rule.scope == scope


def test_a_rule_name_beyond_ascii_that_is_no_control_character_is_accepted() -> None:
    document = {"tokens": {"a": {"keyword": "a"}}, "rules": [_rule(name="\xe9\xa0", any=["a"])]}
    [rule] = matcher_config_from_document(document, file_path=_FILE).rules
    assert rule.name == "\xe9\xa0"


_ONE_CONDITION = "exactly one condition (all/any/not) expected, got {keys}"


@pytest.mark.parametrize(
    ("rule", "key", "message"),
    [
        ("id_segment_exact", "rules[0]", "Input should be a valid dictionary"),
        (_rule(), "rules[0]", _ONE_CONDITION.format(keys=[])),
        (_rule(all=["a"], any=["a"]), "rules[0]", _ONE_CONDITION.format(keys=["all", "any"])),
        (
            {"tier": "catalog", "scope": "unattributed", "any": ["a"]},
            "rules[0].name",
            "Field required",
        ),
        (_rule(name="", any=["a"]), "rules[0].name", "String should have at least 1 character"),
        (_rule(name=62, any=["a"]), "rules[0].name", "Input should be a valid string"),
        (
            _rule(tier="bogus", any=["a"]),
            "rules[0].tier",
            "Input should be 'catalog', 'notify' or 'download'",
        ),
        ({"name": "r", "tier": "notify", "any": ["a"]}, "rules[0].scope", "Field required"),
        (
            _rule(scope="target", any=["a"]),
            "rules[0].scope",
            "Input should be 'segment', 'episode' or 'unattributed'",
        ),
        (_rule(all=["a"], keyword="a"), "rules[0].keyword", "Extra inputs are not permitted"),
    ],
)
def test_a_wrong_rule_is_refused_by_its_key(*, rule: object, key: str, message: str) -> None:
    assert _rule_problems(rule) == [(key, message)]


# Cc: the C0 controls, DEL and the C1 controls.
@pytest.mark.parametrize("name", ["a\tb", "\x1f", "\x85", "\x7f"])
def test_a_control_character_in_a_rule_name_is_refused_without_its_value(name: str) -> None:
    assert _rule_problems(_rule(name=name, any=["a"])) == [
        ("rules[0].name", "holds a control character")
    ]


def test_every_problem_of_the_rules_is_listed() -> None:
    rules = [_rule(name=3, tier="bogus", any=["a"]), _rule(any=["a"], extra=True), "x"]
    assert _problems({"tokens": {"a": {"keyword": "a"}}, "rules": rules}) == [
        ("rules[0].name", "Input should be a valid string"),
        ("rules[0].tier", "Input should be 'catalog', 'notify' or 'download'"),
        ("rules[1].extra", "Extra inputs are not permitted"),
        ("rules[2]", "Input should be a valid dictionary"),
    ]


def test_a_failing_token_cited_by_two_rules_is_its_definitions_problem_alone() -> None:
    document = {
        "tokens": {"t": {"keyword": 3}},
        "rules": [_rule(name="one", any=["t"]), _rule(name="two", all=["t"])],
    }
    assert _problems(document) == [("tokens.t.keyword", "Input should be a valid string")]


def test_no_message_of_the_rules_prints_the_value_received() -> None:
    problems = _rule_problems(_rule(name=["SECRET"], tier="SECRET", scope="SECRET", any=["a"]))
    assert [key for key, _ in problems] == ["rules[0].name", "rules[0].tier", "rules[0].scope"]
    assert all("SECRET" not in message for _, message in problems)


def test_a_rule_gives_its_conditions_operands_and_references() -> None:
    title_hit = {"coverage": "title", "min_coverage": 0.6}
    reference = {"token": "title_hit", "min_coverage": 0.5, "min_similarity": 0.9}
    document = {
        "tokens": {"a": {"keyword": "a"}, "title_hit": title_hit, "not_a": {"not": "a"}},
        "rules": [_rule(all=["a", reference, {"not": {"any": ["not_a", {"token": "a"}]}}])],
    }
    [rule] = matcher_config_from_document(document, file_path=_FILE).rules
    assert rule.condition == AllDefinition(
        operands=(
            "a",
            TokenReference(name="title_hit", min_coverage=0.5, min_similarity=0.9),
            NotDefinition(operand=AnyDefinition(operands=("not_a", TokenReference(name="a")))),
        )
    )


_AT_LEAST_ONE = "List should have at least 1 item after validation, not 0"


@pytest.mark.parametrize(
    ("rule", "key", "message"),
    [
        (_rule(all=[]), "rules[0].all", _AT_LEAST_ONE),
        (_rule(any=[]), "rules[0].any", _AT_LEAST_ONE),
        (_rule(all="a"), "rules[0].all", "Input should be a valid list"),
        (_rule(all=[123]), "rules[0].all[0]", "Input should be a valid string or dictionary"),
        (_rule(**{"not": {"min_coverage": 0.5}}), "rules[0].not.token", "Field required"),
        (
            _rule(all=[{"token": "a", "min_coverage": "0.5"}]),
            "rules[0].all[0].min_coverage",
            "Input should be a valid number",
        ),
        (
            _rule(all=[{"token": "a", "min_similarity": float("nan")}]),
            "rules[0].all[0].min_similarity",
            "Input should be a finite number",
        ),
        (
            _rule(all=[{"token": "a", "min_coverage": 5.0}]),
            "rules[0].all[0].min_coverage",
            "Input should be less than or equal to 1",
        ),
        (
            _rule(all=[{"token": "a", "weight": 1}]),
            "rules[0].all[0].weight",
            "Extra inputs are not permitted",
        ),
        (
            _rule(any=[{"all": ["a"], "not": "a"}]),
            "rules[0].any[0]",
            _ONE_CONDITION.format(keys=["all", "not"]),
        ),
    ],
)
def test_a_wrong_condition_of_a_rule_is_refused_by_its_key(
    *, rule: object, key: str, message: str
) -> None:
    assert _rule_problems(rule) == [(key, message)]


@pytest.mark.parametrize(
    ("token", "key", "message"),
    [
        ({"all": ["a"], "keyword": "a"}, "tokens.t.keyword", "Extra inputs are not permitted"),
        ({"any": ["a"], "not": "a"}, "tokens.t", _ONE_CONDITION.format(keys=["any", "not"])),
        ({"not": 3}, "tokens.t.not", "Input should be a valid string or dictionary"),
    ],
)
def test_a_wrong_condition_token_is_refused_by_its_key(
    *, token: dict[str, Any], key: str, message: str
) -> None:
    assert _token_problems(token) == [(key, message)]


@pytest.mark.parametrize(
    ("old_key", "new_key"), [("min", "min_coverage"), ("fuzz", "min_similarity")]
)
def test_a_token_references_4x_key_is_one_problem_naming_its_new_name(
    *, old_key: str, new_key: str
) -> None:
    rule = _rule(all=[{"token": "a", old_key: 0.5}])
    message = f"was renamed '{new_key}', rename it in matcher.yml"
    assert _rule_problems(rule) == [(f"rules[0].all[0].{old_key}", message)]


def test_every_problem_of_the_conditions_is_listed() -> None:
    document = {
        "tokens": {"a": {"keyword": "a"}, "t": {"any": [3, {"not": []}]}},
        "rules": [_rule(all=[{"token": "a", "min": 0.5}, {"any": []}])],
    }
    assert _problems(document) == [
        ("tokens.t.any[0]", "Input should be a valid string or dictionary"),
        ("tokens.t.any[1].not", "Input should be a valid string or dictionary"),
        ("rules[0].all[0].min", "was renamed 'min_coverage', rename it in matcher.yml"),
        ("rules[0].all[1].any", _AT_LEAST_ONE),
    ]


def test_the_error_chains_no_pydantic_error_which_holds_the_values() -> None:
    with pytest.raises(InvalidConfigError) as raised:
        matcher_config_from_document({"vetoes": "s3cr3t"}, file_path=_FILE)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
