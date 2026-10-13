import re

import pytest

from catalog_matching.config import (
    AllDef,
    AnyDef,
    AttrBetweenDef,
    CoverageDef,
    KeywordDef,
    NotDef,
    RegexDef,
    TokenRef,
)
from catalog_matching.models import FOUND, TARGET_STATUSES
from catalog_matching.validation import (
    CycleError,
    DepthExceededError,
    MatchingConfigError,
    UnknownTokenError,
    parse_matcher_config,
    parse_targets,
    validate_config,
)


def test_parse_leaf_token_defs() -> None:
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
    assert config.tokens["keroro"] == KeywordDef(phrase="keroro")
    assert config.tokens["teletoon"] == RegexDef(pattern="t[eé]l[eé]toon", flags="i")
    assert config.tokens["video"] == RegexDef(pattern="\\.(avi|mkv)$", flags="")
    assert config.tokens["title_hit"] == CoverageDef(
        reference="title", min_coverage=0.6, min_similarity=0.9
    )
    assert config.tokens["small"] == AttrBetweenDef(
        attr="size_mib", min_bound=30.0, max_bound=600.0
    )


def test_parse_composite_token_def() -> None:
    config = parse_matcher_config(
        {
            "tokens": {
                "keroro": {"keyword": "keroro"},
                "titar": {"keyword": "titar"},
                "kt": {"any": ["keroro", "titar"]},
            },
            "rules": [],
        }
    )
    assert config.tokens["kt"] == AnyDef(operands=("keroro", "titar"))


def test_parse_not_token_def() -> None:
    config = parse_matcher_config(
        {"tokens": {"keroro": {"keyword": "keroro"}, "nk": {"not": "keroro"}}, "rules": []}
    )
    assert config.tokens["nk"] == NotDef(operand="keroro")


def test_parse_rule_with_inline_token_ref_and_condition() -> None:
    config = parse_matcher_config(
        {
            "tokens": {
                "title_hit": {"coverage": "title", "min_coverage": 0.6},
                "seg": {"regex": "0*{absolute_number}"},
            },
            "rules": [
                {
                    "name": "numero_titre",
                    "tier": "notify",
                    "scope": "unattributed",
                    "all": ["seg", {"token": "title_hit", "min_coverage": 0.5}],
                }
            ],
        }
    )
    rule = config.rules[0]
    assert rule.name == "numero_titre"
    assert rule.tier == "notify"
    assert rule.condition == AllDef(operands=("seg", TokenRef(name="title_hit", min_coverage=0.5)))


def test_parse_rule_with_nested_inline_condition() -> None:
    config = parse_matcher_config(
        {
            "tokens": {"keroro": {"keyword": "keroro"}, "titar": {"keyword": "titar"}},
            "rules": [
                {
                    "name": "r",
                    "tier": "catalog",
                    "scope": "unattributed",
                    "not": {"any": ["keroro", "titar"]},
                }
            ],
        }
    )
    assert config.rules[0].condition == NotDef(operand=AnyDef(operands=("keroro", "titar")))


def test_unknown_tier_raises_and_names_it() -> None:
    with pytest.raises(MatchingConfigError, match="bogus"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [
                    {"name": "r", "tier": "bogus", "scope": "unattributed", "any": ["keroro"]}
                ],
            }
        )


def test_parse_rule_reads_its_scope() -> None:
    config = parse_matcher_config(
        {
            "tokens": {"keroro": {"keyword": "keroro"}},
            "rules": [{"name": "r", "tier": "notify", "scope": "episode", "any": ["keroro"]}],
        }
    )
    assert config.rules[0].scope == "episode"


def test_rule_without_scope_raises_and_names_the_rule() -> None:
    # A matcher.yml from before scopes must fail at boot, not silently lose its fan-out.
    with pytest.raises(MatchingConfigError, match="rule 'numero_nu' without 'scope'"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [{"name": "numero_nu", "tier": "notify", "any": ["keroro"]}],
            }
        )


def test_unknown_scope_raises_and_names_it() -> None:
    with pytest.raises(MatchingConfigError, match="unknown scope for rule 'r': 'target'"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [{"name": "r", "tier": "notify", "scope": "target", "any": ["keroro"]}],
            }
        )


def test_attr_between_unknown_attr_raises_and_names_it() -> None:
    with pytest.raises(MatchingConfigError, match="codec"):
        parse_matcher_config({"tokens": {"c": {"attr_between": "codec", "min": 1}}, "rules": []})


def test_unknown_token_definition_shape_raises() -> None:
    with pytest.raises(MatchingConfigError, match="unknown token shape"):
        parse_matcher_config({"tokens": {"x": {"frobnicate": "y"}}, "rules": []})


def test_token_def_with_multiple_keys_raises() -> None:
    with pytest.raises(MatchingConfigError, match="exactly one type-key"):
        parse_matcher_config({"tokens": {"x": {"keyword": "a", "regex": "b"}}, "rules": []})


def test_override_on_non_coverage_token_raises() -> None:
    with pytest.raises(MatchingConfigError, match="kw"):
        parse_matcher_config(
            {
                "tokens": {"kw": {"keyword": "keroro"}},
                "rules": [
                    {
                        "name": "r",
                        "tier": "catalog",
                        "scope": "unattributed",
                        "all": [{"token": "kw", "min_coverage": 0.5}],
                    }
                ],
            }
        )


def test_rule_without_condition_key_raises() -> None:
    with pytest.raises(MatchingConfigError, match="condition"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [{"name": "r", "tier": "catalog", "scope": "unattributed"}],
            }
        )


def test_rule_with_two_condition_keys_raises() -> None:
    with pytest.raises(MatchingConfigError, match="exactly one condition"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [
                    {
                        "name": "r",
                        "tier": "catalog",
                        "scope": "unattributed",
                        "all": ["keroro"],
                        "any": ["keroro"],
                    }
                ],
            }
        )


def test_rule_with_empty_all_is_rejected() -> None:
    # config-validation#0: AllMatcher([]).matches() == all([]) == True → a rule 'all: []'
    # would unconditionally match EVERY file (here in tier=download → auto-download).
    # EBNF §8.3 requires >=1 operand; fail-fast must reject it at load time.
    with pytest.raises(MatchingConfigError, match="at least one operand"):
        parse_matcher_config(
            {"rules": [{"name": "pwn", "tier": "download", "scope": "unattributed", "all": []}]}
        )


def test_rule_with_empty_any_is_rejected() -> None:
    # Same fail-fast gap for 'any: []' (EBNF §8.3: >=1 operand), degenerate config.
    with pytest.raises(MatchingConfigError, match="at least one operand"):
        parse_matcher_config(
            {"rules": [{"name": "pwn", "tier": "download", "scope": "unattributed", "any": []}]}
        )


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
    # Same bound for a min_coverage/min_similarity override on a TokenRef (coverage).
    with pytest.raises(MatchingConfigError, match=r"\[0, 1\]"):
        parse_matcher_config(
            {
                "tokens": {"cov": {"coverage": "title", "min_coverage": 0.5}},
                "rules": [
                    {
                        "name": "r",
                        "tier": "catalog",
                        "scope": "unattributed",
                        "all": [{"token": "cov", "min_coverage": 5.0}],
                    }
                ],
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
    coverage_token: dict[str, object], old_key: str, new_key: str
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
    old_key: str, new_key: str
) -> None:
    message = (
        f"operand {{token: 'cov'}}: key '{old_key}' was renamed '{new_key}', "
        "rename it in matcher.yml"
    )
    with pytest.raises(MatchingConfigError, match=re.escape(message)):
        parse_matcher_config(
            {
                "tokens": {"cov": {"coverage": "title", "min_coverage": 0.5}},
                "rules": [
                    {
                        "name": "r",
                        "tier": "catalog",
                        "scope": "unattributed",
                        "all": [{"token": "cov", old_key: 0.5}],
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("old_attr", "new_attr"), [("size_mb", "size_mib"), ("duration_sec", "duration_seconds")]
)
def test_a_4x_attr_between_attribute_is_refused_with_its_new_name(
    old_attr: str, new_attr: str
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


def test_token_ref_missing_name_raises() -> None:
    with pytest.raises(MatchingConfigError, match="token"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [
                    {
                        "name": "r",
                        "tier": "catalog",
                        "scope": "unattributed",
                        "all": [{"min_coverage": 0.5}],
                    }
                ],
            }
        )


def test_operand_wrong_type_raises() -> None:
    with pytest.raises(MatchingConfigError, match="operand"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [{"name": "r", "tier": "catalog", "scope": "unattributed", "all": [123]}],
            }
        )


def test_parse_targets_builds_segments_with_per_segment_status() -> None:
    targets = parse_targets(
        {
            "episodes": [
                {
                    "season": 2,
                    "seasonal_number": 11,
                    "absolute_number": 62,
                    "segments": [
                        {"letter": "A", "title": "Les demoiselles", "status": "found"},
                        {"letter": "B", "title": "Le grand combat"},
                    ],
                }
            ]
        }
    )
    assert len(targets) == 2
    a, b = targets
    assert a.target_id == "062A"
    assert a.seasonal_number == 11
    assert a.absolute_number == 62
    assert a.status == "found"  # status SPECIFIC to segment A
    assert b.target_id == "062B"
    assert b.status == "lost"  # default, B not marked


def test_parse_targets_requires_seasonal_number() -> None:
    with pytest.raises(MatchingConfigError, match="seasonal_number"):
        parse_targets(
            {
                "episodes": [
                    {
                        "season": 1,
                        "absolute_number": 5,
                        "segments": [{"letter": "a", "title": "x"}],
                    }
                ]
            }
        )


def test_parse_targets_requires_absolute_number() -> None:
    with pytest.raises(MatchingConfigError, match="absolute_number"):
        parse_targets(
            {
                "episodes": [
                    {
                        "season": 1,
                        "seasonal_number": 5,
                        "segments": [{"letter": "a", "title": "x"}],
                    }
                ]
            }
        )


def test_parse_targets_default_status_is_lost() -> None:
    targets = parse_targets(
        {
            "episodes": [
                {
                    "season": 1,
                    "seasonal_number": 5,
                    "absolute_number": 5,
                    "segments": [{"letter": "a", "title": "x"}],
                }
            ]
        }
    )
    assert targets[0].status == "lost"


def test_target_statuses_is_the_closed_lost_found_set() -> None:
    assert frozenset({"lost", "found"}) == TARGET_STATUSES
    assert FOUND in TARGET_STATUSES


@pytest.mark.parametrize("status", ["complete", "partial", ""])
def test_parse_targets_rejects_a_status_outside_the_closed_set(status: str) -> None:
    with pytest.raises(MatchingConfigError, match=f"status {status!r}"):
        parse_targets(
            {
                "episodes": [
                    {
                        "season": 1,
                        "seasonal_number": 5,
                        "absolute_number": 5,
                        "segments": [{"letter": "a", "title": "x", "status": status}],
                    }
                ]
            }
        )


def test_parse_targets_episode_without_segments() -> None:
    targets = parse_targets(
        {"episodes": [{"season": 1, "seasonal_number": 1, "absolute_number": 1}]}
    )
    assert targets == ()


def test_parse_targets_duplicate_target_id_raises() -> None:
    with pytest.raises(MatchingConfigError, match="duplicate"):
        parse_targets(
            {
                "episodes": [
                    {
                        "season": 2,
                        "seasonal_number": 11,
                        "absolute_number": 62,
                        "segments": [
                            {"letter": "a", "title": "x"},
                            {"letter": "A", "title": "y"},
                        ],
                    }
                ]
            }
        )


def test_parse_targets_builds_mono_episode_target() -> None:
    targets = parse_targets(
        {
            "episodes": [
                {
                    "season": 1,
                    "seasonal_number": 10,
                    "absolute_number": 10,
                    "segments": [{"letter": "A", "title": "x"}],
                }
            ]
        }
    )
    assert [t.target_id for t in targets] == ["010A"]


def test_parse_targets_builds_two_segment_targets() -> None:
    targets = parse_targets(
        {
            "episodes": [
                {
                    "season": 2,
                    "seasonal_number": 11,
                    "absolute_number": 62,
                    "segments": [
                        {"letter": "A", "title": "x"},
                        {"letter": "B", "title": "y"},
                    ],
                }
            ]
        }
    )
    assert [t.target_id for t in targets] == ["062A", "062B"]


def test_regex_with_date_alt_placeholder_is_rejected() -> None:
    # {date_alt} removed: a token using it fails at load time (unknown placeholder).
    with pytest.raises(MatchingConfigError, match="date_alt"):
        parse_matcher_config({"tokens": {"air": {"regex": "{date_alt}"}}, "rules": []})


def test_parse_targets_missing_episodes_raises() -> None:
    with pytest.raises(MatchingConfigError, match="episodes"):
        parse_targets({})


def test_parse_targets_missing_required_segment_field_raises() -> None:
    with pytest.raises(MatchingConfigError, match="title"):
        parse_targets(
            {
                "episodes": [
                    {
                        "season": 1,
                        "seasonal_number": 5,
                        "absolute_number": 5,
                        "segments": [{"letter": "a"}],
                    }
                ]
            }
        )


# --- Branch-coverage leftovers ---


def test_token_def_non_mapping_raises() -> None:
    """_require_mapping raises MatchingConfigError if the token def is not a mapping."""
    with pytest.raises(MatchingConfigError, match="mapping"):
        parse_matcher_config({"tokens": {"x": "not-a-dict"}, "rules": []})


def test_composite_token_def_multiple_condition_keys_raises() -> None:
    """_parse_condition raises if a composite token contains 2+ condition keys."""
    with pytest.raises(MatchingConfigError, match="exactly one condition"):
        parse_matcher_config({"tokens": {"x": {"all": ["a"], "any": ["b"]}}, "rules": []})


def test_all_body_non_list_raises() -> None:
    """_parse_condition raises if the body of 'all' is not a list."""
    with pytest.raises(MatchingConfigError, match="list"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [
                    {"name": "r", "tier": "catalog", "scope": "unattributed", "all": "keroro"}
                ],
            }
        )


def test_coverage_token_missing_min_raises() -> None:
    """_parse_token_def raises if a coverage does not declare 'min_coverage'."""
    with pytest.raises(MatchingConfigError, match="'min_coverage'"):
        parse_matcher_config({"tokens": {"t": {"coverage": "title"}}, "rules": []})


def test_rule_without_name_raises() -> None:
    """_parse_rule raises if a rule has no 'name'."""
    with pytest.raises(MatchingConfigError, match="name"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [{"tier": "catalog", "scope": "unattributed", "any": ["keroro"]}],
            }
        )


def test_rules_non_list_raises() -> None:
    """parse_matcher_config raises if 'rules' is not a list."""
    with pytest.raises(MatchingConfigError, match="rules"):
        parse_matcher_config({"tokens": {}, "rules": "not-a-list"})


def test_token_ref_with_coverage_token_no_override_ok() -> None:
    """TokenRef on a coverage without an override: valid, no error."""
    config = parse_matcher_config(
        {
            "tokens": {"title_hit": {"coverage": "title", "min_coverage": 0.6}},
            "rules": [
                {
                    "name": "r",
                    "tier": "catalog",
                    "scope": "unattributed",
                    "all": [{"token": "title_hit"}],
                }
            ],
        }
    )
    assert config.rules[0].name == "r"


# --- Task 6: graph validation (DAG, depth, RE2 compile-check) ---


def test_unknown_token_reference_raises_and_names_it() -> None:
    with pytest.raises(UnknownTokenError, match="ghost"):
        parse_matcher_config(
            {
                "tokens": {"kt": {"any": ["keroro", "ghost"]}, "keroro": {"keyword": "keroro"}},
                "rules": [],
            }
        )


def test_unknown_token_in_rule_raises() -> None:
    with pytest.raises(UnknownTokenError, match="ghost"):
        parse_matcher_config(
            {
                "tokens": {"keroro": {"keyword": "keroro"}},
                "rules": [
                    {
                        "name": "r",
                        "tier": "catalog",
                        "scope": "unattributed",
                        "all": ["keroro", "ghost"],
                    }
                ],
            }
        )


def test_direct_cycle_is_detected_and_named() -> None:
    with pytest.raises(CycleError) as excinfo:
        parse_matcher_config({"tokens": {"a": {"any": ["b"]}, "b": {"any": ["a"]}}, "rules": []})
    message = str(excinfo.value)
    assert "a -> b -> a" in message or "b -> a -> b" in message


def test_self_cycle_is_detected() -> None:
    with pytest.raises(CycleError, match="loop"):
        parse_matcher_config({"tokens": {"loop": {"any": ["loop"]}}, "rules": []})


def test_acyclic_composite_graph_validates() -> None:
    config = parse_matcher_config(
        {
            "tokens": {
                "keroro": {"keyword": "keroro"},
                "titar": {"keyword": "titar"},
                "kt": {"any": ["keroro", "titar"]},
                "deep": {"all": ["kt", "keroro"]},
            },
            "rules": [{"name": "r", "tier": "catalog", "scope": "unattributed", "any": ["deep"]}],
        }
    )
    assert "deep" in config.tokens


def test_regex_compile_check_rejects_bad_pattern() -> None:
    with pytest.raises(MatchingConfigError, match="not compilable"):
        parse_matcher_config({"tokens": {"bad": {"regex": "(unbalanced"}}, "rules": []})


def test_regex_unknown_placeholder_rejected_at_load() -> None:
    with pytest.raises(MatchingConfigError, match="bogus"):
        parse_matcher_config({"tokens": {"bad": {"regex": "n {bogus}"}}, "rules": []})


def test_regex_with_known_placeholders_validates() -> None:
    config = parse_matcher_config(
        {"tokens": {"seg": {"regex": "n[°o]?\\s*0*{absolute_number}\\s*{letter}"}}, "rules": []}
    )
    assert "seg" in config.tokens


def test_the_4x_segment_placeholder_is_refused_with_its_new_name() -> None:
    message = (
        "token 'seg': placeholder '{segment}' was renamed '{letter}', rename it in matcher.yml"
    )
    with pytest.raises(MatchingConfigError, match=re.escape(message)):
        parse_matcher_config({"tokens": {"seg": {"regex": "n°{absolute_number}{segment}"}}})


def test_depth_within_bound_validates() -> None:
    # Chain a -> b -> c (depth 3) with max_depth=3: OK.
    config = parse_matcher_config(
        {
            "tokens": {
                "c": {"keyword": "x"},
                "b": {"any": ["c"]},
                "a": {"any": ["b"]},
            },
            "rules": [],
        }
    )
    validate_config(config, max_depth=3)


def test_depth_exceeded_raises() -> None:
    config = parse_matcher_config(
        {
            "tokens": {
                "c": {"keyword": "x"},
                "b": {"any": ["c"]},
                "a": {"any": ["b"]},
            },
            "rules": [],
        }
    )
    with pytest.raises(DepthExceededError, match="depth"):
        validate_config(config, max_depth=2)


def test_default_max_depth_is_32() -> None:
    # A chain of 33 tokens exceeds the default 32.
    tokens: dict[str, object] = {"t0": {"keyword": "x"}}
    for i in range(1, 34):
        tokens[f"t{i}"] = {"any": [f"t{i - 1}"]}
    with pytest.raises(DepthExceededError):
        parse_matcher_config({"tokens": tokens, "rules": []})


def test_deep_chain_root_first_caught_by_dfs_guard() -> None:
    # Root-first order: _check_acyclic's DFS descends the whole chain, so the
    # len(stack)>=max_depth guard raises DepthExceededError before any RecursionError.
    tokens: dict[str, object] = {}
    for i in range(40, 0, -1):  # t40 (root) defined first, t0 (leaf) last
        tokens[f"t{i}"] = {"any": [f"t{i - 1}"]}
    tokens["t0"] = {"keyword": "x"}
    with pytest.raises(DepthExceededError):
        parse_matcher_config({"tokens": tokens, "rules": []})


def test_empty_config_validates() -> None:
    # Empty token table: _max_resolution_depth must return 0 (default), no error.
    config = parse_matcher_config({"tokens": {}, "rules": []})
    assert config.tokens == {}


def test_coverage_override_forward_reference_in_composite_validates() -> None:
    # Regression: a composite token referencing {token: cov, min: …} where cov is
    # defined AFTER must NOT be rejected (override validation deferred to the graph).
    config = parse_matcher_config(
        {
            "tokens": {
                "combo": {"any": [{"token": "title_hit", "min_coverage": 0.4}, "keroro"]},
                "title_hit": {"coverage": "title", "min_coverage": 0.6},
                "keroro": {"keyword": "keroro"},
            },
            "rules": [],
        }
    )
    assert "combo" in config.tokens


# --- fragments: raw regex text substituted into regex tokens at parse time ---


def test_fragment_is_expanded_into_regex_tokens_at_parse_time() -> None:
    config = parse_matcher_config(
        {
            "fragments": {"marker": "(?:n°|#)\\s*"},
            "tokens": {"explicit": {"regex": "{marker}\\d|\\b{marker}x{2,3}"}},
        }
    )
    assert config.tokens["explicit"] == RegexDef(pattern="(?:n°|#)\\s*\\d|\\b(?:n°|#)\\s*x{2,3}")


def test_fragment_keeps_its_target_placeholders_for_per_target_interpolation() -> None:
    config = parse_matcher_config(
        {"fragments": {"own": "0*{absolute_number}"}, "tokens": {"id": {"regex": "n°{own}"}}}
    )
    assert config.tokens["id"] == RegexDef(pattern="n°0*{absolute_number}")


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
        parse_matcher_config({"tokens": {"a": {"keyword": "a"}}, "vetoes": ["ghost"]})


def test_duplicate_veto_is_rejected() -> None:
    with pytest.raises(MatchingConfigError, match="duplicate veto: 'a'"):
        parse_matcher_config({"tokens": {"a": {"keyword": "a"}}, "vetoes": ["a", "a"]})


def test_vetoes_section_must_be_a_list() -> None:
    with pytest.raises(MatchingConfigError, match="'vetoes' section: list expected"):
        parse_matcher_config({"tokens": {"a": {"keyword": "a"}}, "vetoes": "a"})
