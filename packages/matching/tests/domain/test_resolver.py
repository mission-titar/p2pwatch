from catalog_matching.domain.matchers import AttributeBetweenMatcher, CoverageMatcher, RegexMatcher
from catalog_matching.domain.models import FileCandidate, TargetSegment
from catalog_matching.domain.resolver import MatcherResolver
from catalog_matching.domain.validation import parse_matcher_config

_TARGET = TargetSegment(
    season=2,
    seasonal_number=11,
    absolute_number=62,
    letter="a",
    title="Les demoiselles cambrioleuses",
)


def _resolver_from(raw: dict[str, object]) -> MatcherResolver:
    return MatcherResolver(parse_matcher_config(raw))


def test_resolve_keyword_token() -> None:
    resolver = _resolver_from({"tokens": {"keroro": {"keyword": "keroro"}}, "rules": []})
    matcher = resolver.resolve_token("keroro", target=_TARGET)
    assert matcher.matches(FileCandidate(filename="Keroro 062A.avi")) is True
    assert matcher.matches(FileCandidate(filename="autre.avi")) is False


def test_resolve_regex_token_interpolates_per_target() -> None:
    resolver = _resolver_from(
        {"tokens": {"seg": {"regex": "n[°o]?\\s*0*{absolute_number}\\s*{letter}"}}, "rules": []}
    )
    matcher = resolver.resolve_token("seg", target=_TARGET)
    assert isinstance(matcher, RegexMatcher)
    assert matcher.matches(FileCandidate(filename="Keroro N°062A.avi")) is True
    # Another target (number 7) produces a distinct matcher that does not match 062.
    other = TargetSegment(season=2, seasonal_number=7, absolute_number=7, letter="b", title="x")
    assert (
        resolver.resolve_token("seg", target=other).matches(
            FileCandidate(filename="Keroro N°062A.avi")
        )
        is False
    )


def test_resolve_coverage_binds_title() -> None:
    resolver = _resolver_from(
        {"tokens": {"title_hit": {"coverage": "title", "min_coverage": 0.6}}, "rules": []}
    )
    matcher = resolver.resolve_token("title_hit", target=_TARGET)
    assert isinstance(matcher, CoverageMatcher)
    candidate = FileCandidate(filename="062A Les demoiselles cambrioleuses.avi")
    assert matcher.matches(candidate) is True
    assert matcher.coverage(candidate) == 1.0


def test_resolve_coverage_non_title_reference_used_literally() -> None:
    # A reference != "title" is used as-is as the reference text.
    resolver = _resolver_from(
        {"tokens": {"lit": {"coverage": "keroro titar", "min_coverage": 0.5}}, "rules": []}
    )
    matcher = resolver.resolve_token("lit", target=_TARGET)
    assert isinstance(matcher, CoverageMatcher)
    assert matcher.matches(FileCandidate(filename="keroro titar 062.avi")) is True


def test_resolve_attr_between_token() -> None:
    resolver = _resolver_from(
        {"tokens": {"sz": {"attr_between": "size_mib", "min": 30, "max": 600}}, "rules": []}
    )
    matcher = resolver.resolve_token("sz", target=_TARGET)
    assert isinstance(matcher, AttributeBetweenMatcher)
    assert matcher.matches(FileCandidate(filename="x.avi", size_mib=120.0)) is True
    assert matcher.matches(FileCandidate(filename="x.avi", size_mib=5.0)) is False


def test_resolve_composite_any_token() -> None:
    resolver = _resolver_from(
        {
            "tokens": {
                "keroro": {"keyword": "keroro"},
                "titar": {"keyword": "titar"},
                "kt": {"any": ["keroro", "titar"]},
            },
            "rules": [],
        }
    )
    matcher = resolver.resolve_token("kt", target=_TARGET)
    assert matcher.matches(FileCandidate(filename="titar only.avi")) is True
    assert matcher.matches(FileCandidate(filename="ni l un ni l autre.avi")) is False


def test_resolve_composite_all_and_not() -> None:
    resolver = _resolver_from(
        {
            "tokens": {
                "keroro": {"keyword": "keroro"},
                "titar": {"keyword": "titar"},
                "k_not_t": {"all": ["keroro", {"not": "titar"}]},
            },
            "rules": [],
        }
    )
    matcher = resolver.resolve_token("k_not_t", target=_TARGET)
    assert matcher.matches(FileCandidate(filename="keroro seul.avi")) is True
    assert matcher.matches(FileCandidate(filename="keroro titar.avi")) is False


def test_resolve_rule_condition() -> None:
    resolver = _resolver_from(
        {
            "tokens": {"keroro": {"keyword": "keroro"}, "titar": {"keyword": "titar"}},
            "rules": [
                {
                    "name": "r",
                    "tier": "catalog",
                    "scope": "unattributed",
                    "all": ["keroro", "titar"],
                }
            ],
        }
    )
    rule = resolver.config.rules[0]
    matcher = resolver.resolve_rule(rule, target=_TARGET)
    assert matcher.matches(FileCandidate(filename="keroro titar 062.avi")) is True
    assert matcher.matches(FileCandidate(filename="keroro seul.avi")) is False


def test_token_reference_override_applies_min() -> None:
    # significant title = {demoiselles, cambrioleuses} (2 words, "les" is a stopword).
    # "demoiselles" alone covers 1/2 = 0.5: 0.34 <= 0.5 (match) but 0.6 > 0.5 (no match).
    resolver = _resolver_from(
        {
            "tokens": {"title_hit": {"coverage": "title", "min_coverage": 0.6}},
            "rules": [
                {
                    "name": "low",
                    "tier": "notify",
                    "scope": "unattributed",
                    "all": [{"token": "title_hit", "min_coverage": 0.34}],
                }
            ],
        }
    )
    matcher = resolver.resolve_rule(resolver.config.rules[0], target=_TARGET)
    candidate = FileCandidate(filename="quelque chose demoiselles xyz.avi")
    assert matcher.matches(candidate) is True
    # Without override (min_coverage 0.6), the same candidate would NOT match.
    strict = resolver.resolve_token("title_hit", target=_TARGET)
    assert strict.matches(candidate) is False


def test_token_reference_override_applies_fuzz() -> None:
    # min_similarity override 0.99 via {token: title_hit, min_similarity: 0.99}: a typo
    # 'demoiseles'
    # (ratio ~0.95 vs 'demoiselles') is no longer counted as covered, so
    # 'cambrioleuses' alone = 1/2 = 0.5 < 0.6 -> no match.
    resolver = _resolver_from(
        {
            "tokens": {"title_hit": {"coverage": "title", "min_coverage": 0.6}},
            "rules": [
                {
                    "name": "f",
                    "tier": "notify",
                    "scope": "unattributed",
                    "all": [{"token": "title_hit", "min_similarity": 0.99}],
                }
            ],
        }
    )
    matcher = resolver.resolve_rule(resolver.config.rules[0], target=_TARGET)
    typo = FileCandidate(filename="les demoiseles cambrioleuses 062.avi")
    assert matcher.matches(typo) is False
    # Without override (default min_similarity 0.85), the typo is covered -> both tokens -> match.
    lax = resolver.resolve_token("title_hit", target=_TARGET)
    assert lax.matches(typo) is True


def test_token_reference_without_override_resolves_token_as_is() -> None:
    resolver = _resolver_from(
        {
            "tokens": {"title_hit": {"coverage": "title", "min_coverage": 0.6}},
            "rules": [
                {
                    "name": "plain",
                    "tier": "notify",
                    "scope": "unattributed",
                    "all": [{"token": "title_hit"}],
                }
            ],
        }
    )
    matcher = resolver.resolve_rule(resolver.config.rules[0], target=_TARGET)
    candidate = FileCandidate(filename="Les demoiselles cambrioleuses 062A.avi")
    assert matcher.matches(candidate) is True


def test_resolve_all_returns_every_token_and_rule_matcher() -> None:
    resolver = _resolver_from(
        {
            "tokens": {"keroro": {"keyword": "keroro"}, "seg": {"regex": "0*{absolute_number}"}},
            "rules": [{"name": "r", "tier": "catalog", "scope": "unattributed", "any": ["keroro"]}],
        }
    )
    resolved = resolver.resolve_target(_TARGET)
    assert resolved.target is _TARGET
    assert set(resolved.matcher_by_token_name) == {"keroro", "seg"}
    assert set(resolved.matcher_by_rule_name) == {"r"}
    assert (
        resolved.matcher_by_token_name["keroro"].matches(FileCandidate(filename="keroro.avi"))
        is True
    )
    assert resolved.matcher_by_rule_name["r"].matches(FileCandidate(filename="keroro.avi")) is True
