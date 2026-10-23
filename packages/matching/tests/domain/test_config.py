import dataclasses

import pytest

from catalog_matching.domain.config import (
    SCOPES,
    TIER_RANK,
    TIERS,
    AllDefinition,
    AnyDefinition,
    AttributeBetweenDefinition,
    CoverageDefinition,
    KeywordDefinition,
    MatcherConfig,
    NotDefinition,
    RegexDefinition,
    Rule,
    TokenReference,
)


def test_keyword_definition_holds_phrase() -> None:
    assert KeywordDefinition(phrase="keroro").phrase == "keroro"


def test_regex_definition_defaults_flags_to_i() -> None:
    assert RegexDefinition(pattern="teletoon").flags == "i"
    assert RegexDefinition(pattern="teletoon", flags="").flags == ""


def test_coverage_definition_defaults() -> None:
    cov = CoverageDefinition(reference="title", min_coverage=0.6)
    assert cov.reference == "title"
    assert cov.min_coverage == 0.6
    assert cov.min_similarity == 0.85


def test_attribute_between_definition_holds_bounds() -> None:
    ab = AttributeBetweenDefinition(attr="size_mib", min_bound=30.0, max_bound=600.0)
    assert ab.attr == "size_mib"
    assert ab.min_bound == 30.0
    assert ab.max_bound == 600.0
    assert AttributeBetweenDefinition(attr="size_mib").min_bound is None
    assert AttributeBetweenDefinition(attr="size_mib").max_bound is None


def test_composite_defs_hold_operands() -> None:
    comp = AnyDefinition(operands=("keroro", "titar"))
    assert comp.operands == ("keroro", "titar")
    assert AllDefinition(operands=()).operands == ()
    assert NotDefinition(operand="keroro").operand == "keroro"


def test_token_reference_overrides_default_to_none() -> None:
    ref = TokenReference(name="title_hit")
    assert ref.name == "title_hit"
    assert ref.min_coverage is None
    assert ref.min_similarity is None
    assert TokenReference(name="title_hit", min_coverage=0.4).min_coverage == 0.4


def test_rule_holds_name_tier_scope_condition() -> None:
    rule = Rule(
        name="keroro_large",
        tier="catalog",
        scope="unattributed",
        condition=AnyDefinition(operands=("keroro_titar",)),
    )
    assert rule.name == "keroro_large"
    assert rule.tier == "catalog"
    assert rule.scope == "unattributed"
    assert isinstance(rule.condition, AnyDefinition)


def test_matcher_config_holds_tokens_and_rules() -> None:
    config = MatcherConfig(
        tokens={"keroro": KeywordDefinition(phrase="keroro")},
        rules=(
            Rule(
                name="r",
                tier="catalog",
                scope="unattributed",
                condition=AnyDefinition(operands=("keroro",)),
            ),
        ),
    )
    assert config.tokens["keroro"] == KeywordDefinition(phrase="keroro")
    assert len(config.rules) == 1


def test_defs_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        KeywordDefinition(phrase="x").phrase = "y"  # type: ignore[misc]


def test_matcher_config_is_frozen() -> None:
    config = MatcherConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.rules = ()  # type: ignore[misc]


def test_scopes_is_the_closed_segment_episode_unattributed_set() -> None:
    assert frozenset({"segment", "episode", "unattributed"}) == SCOPES


def test_tier_rank_orders_download_above_notify_above_catalog() -> None:
    assert TIER_RANK["download"] > TIER_RANK["notify"]
    assert TIER_RANK["notify"] > TIER_RANK["catalog"]


def test_tier_rank_catalog_is_lowest() -> None:
    assert TIER_RANK["catalog"] < TIER_RANK["download"]
    assert TIER_RANK["catalog"] < TIER_RANK["notify"]


def test_tier_rank_covers_exactly_the_valid_tiers() -> None:
    # Consistency: every licit tier (TIERS) has a rank, and no orphan rank.
    assert set(TIER_RANK) == TIERS


def test_matcher_config_has_no_vetoes_by_default() -> None:
    assert MatcherConfig().vetoes == ()
