"""Load-time validation (fail-fast): parsed YAML schema -> config model.

PURE domain: receives already-parsed structures (``dict``/``list``), does not import
``yaml``, does not touch the disk. Covers spec §8.4 (load-time validation) on the schema
side + local validations (closed tier, ``attr_between`` enum, coverage-only override). Graph
validation (DAG/depth) and the regex compile-check are added in Task 6.
"""

import re
from typing import Any

from catalog_matching.domain.config import (
    SCOPES,
    TIERS,
    AllDefinition,
    AnyDefinition,
    AttributeBetweenDefinition,
    Condition,
    CoverageDefinition,
    KeywordDefinition,
    MatcherConfig,
    NotDefinition,
    Operand,
    RegexDefinition,
    Rule,
    TokenDefinition,
    TokenReference,
)
from catalog_matching.domain.interpolation import (
    PLACEHOLDER,
    TARGET_PLACEHOLDERS,
    InterpolationError,
    interpolate,
)
from catalog_matching.domain.matchers import READERS_BY_ATTR
from catalog_matching.domain.models import LOST, TARGET_STATUSES, TargetSegment

_CONDITION_KEYS = ("all", "any", "not")
# 4.x names, refused at load with their 5.0 name (``{segment}`` too, in _check_regexes_compile).
_RENAMED_COVERAGE_KEYS = {"min": "min_coverage", "fuzz": "min_similarity"}
_RENAMED_ATTRS = {"size_mb": "size_mib", "duration_sec": "duration_seconds"}


class MatchingConfigError(Exception):
    """Fatal configuration error at load time (schema, tier, enum, override)."""


class UnknownTokenError(MatchingConfigError):
    """A reference points to a token missing from the table."""


class CycleError(MatchingConfigError):
    """The token->token reference graph contains a cycle (the message names it)."""


class DepthExceededError(MatchingConfigError):
    """The resolution depth exceeds the bound (default 32)."""


def _require_mapping(node: Any, error_label: str) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise MatchingConfigError(f"{error_label}: mapping expected, got {type(node).__name__}")
    return node


def _require_key(mapping: dict[str, Any], key: str, error_label: str) -> Any:
    if key not in mapping:
        raise MatchingConfigError(f"{error_label}: key {key!r} missing")
    return mapping[key]


def _parse_operand(raw: Any) -> Operand:
    """An operand: bare token name (str), ``{token: …}`` (TokenReference), or inline condition."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        if any(key in raw for key in _CONDITION_KEYS):
            return _parse_condition(raw)
        # Treated as a token reference (with or without the "token" key): _parse_token_reference
        # will raise MatchingConfigError if the "token" key is missing or invalid.
        return _parse_token_reference(raw)
    raise MatchingConfigError(f"operand of invalid type: {type(raw).__name__} ({raw!r})")


def _number(raw: Any, error_label: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as error:
        raise MatchingConfigError(f"{error_label}: number expected, got {raw!r}") from error


def _integer(raw: Any, error_label: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as error:
        raise MatchingConfigError(f"{error_label}: integer expected, got {raw!r}") from error


def _require_unit_fraction(fraction: float, error_label: str) -> float:
    """Validates that a fraction (min_coverage, min_similarity) is in [0, 1] (fail-fast §8.4).

    Outside [0, 1], the rule is silently inert (threshold never reached): that is a config
    error (typically a percentage entered for a fraction), rejected at load time.
    """
    if not 0.0 <= fraction <= 1.0:
        raise MatchingConfigError(f"{error_label} must be in [0, 1], got {fraction}")
    return fraction


def _refuse_renamed_coverage_keys(mapping: dict[str, Any], error_label: str) -> None:
    for old_key, new_key in _RENAMED_COVERAGE_KEYS.items():
        if old_key in mapping:
            raise MatchingConfigError(
                f"{error_label}: key {old_key!r} was renamed {new_key!r}, rename it in matcher.yml"
            )


def _parse_token_reference(raw: dict[str, Any]) -> TokenReference:
    name = raw.get("token")
    if not isinstance(name, str):
        raise MatchingConfigError(f"operand {{token: …}} without a valid token name: {raw!r}")
    _refuse_renamed_coverage_keys(raw, f"operand {{token: {name!r}}}")
    min_coverage = raw.get("min_coverage")
    min_similarity = raw.get("min_similarity")
    # The legality of an override (coverage-only, cf. EBNF §8.3) is checked at the
    # graph level (validate_config), not here: parsing stays purely structural and independent
    # of the token definition order (forward references allowed). The [0, 1] BOUNDS, on the
    # other hand, are structural → validated here.
    return TokenReference(
        name=name,
        min_coverage=(
            None
            if min_coverage is None
            else _require_unit_fraction(
                _number(min_coverage, f"'min_coverage' override of {name!r}"),
                f"'min_coverage' override of {name!r}",
            )
        ),
        min_similarity=(
            None
            if min_similarity is None
            else _require_unit_fraction(
                _number(min_similarity, f"'min_similarity' override of {name!r}"),
                f"'min_similarity' override of {name!r}",
            )
        ),
    )


def _parse_condition(raw: dict[str, Any]) -> Condition:
    present = [key for key in _CONDITION_KEYS if key in raw]
    if len(present) != 1:
        raise MatchingConfigError(f"exactly one condition (all/any/not) expected, got {present!r}")
    key = present[0]
    body = raw[key]
    if key == "not":
        return NotDefinition(operand=_parse_operand(body))
    if not isinstance(body, list):
        raise MatchingConfigError(f"'{key}:' expects a list of operands, got {type(body).__name__}")
    if not body:
        # EBNF §8.3: operand (',' operand)* = at least one operand. An empty list would give
        # AllMatcher([]).matches()==all([])==True (matches EVERYTHING) or AnyMatcher([])==False
        # (mute): degenerate config, rejected at load time (fail-fast §8.4). all([])/any([])
        # remains the legitimate internal semantics of the combinators - it is the empty CONFIG
        # that we forbid.
        raise MatchingConfigError(f"'{key}:' requires at least one operand (empty list received)")
    operands = tuple(_parse_operand(raw_operand) for raw_operand in body)
    if key == "all":
        return AllDefinition(operands=operands)
    return AnyDefinition(operands=operands)


def _optional_float(mapping: dict[str, Any], key: str, error_label: str) -> float | None:
    """Reads an optional float bound (``None`` if absent)."""
    bound = mapping.get(key)
    return None if bound is None else _number(bound, f"{error_label}: key {key!r}")


def _parse_fragments(raw: Any) -> dict[str, str]:
    """``fragments:`` name -> raw regex text; one level only (no fragment in a fragment)."""
    fragments = {
        str(name): str(text) for name, text in _require_mapping(raw, "'fragments' section").items()
    }
    for name, text in fragments.items():
        if name in TARGET_PLACEHOLDERS:
            raise MatchingConfigError(f"fragment {name!r} collides with a target placeholder")
        for fragment_name in PLACEHOLDER.findall(text):
            if fragment_name in fragments:
                raise MatchingConfigError(
                    f"fragment {name!r} references fragment {fragment_name!r}"
                )
    return fragments


def _expand_fragments(pattern: str, fragments: dict[str, str]) -> str:
    """Substitutes ``{fragment}``; target placeholders are left for per-target interpolation."""
    return PLACEHOLDER.sub(lambda m: fragments.get(m.group(1), m.group(0)), pattern)


def _parse_token_definition(
    token_name: str, raw: Any, fragments: dict[str, str]
) -> TokenDefinition:
    """Dispatch of a token definition: composite (all/any/not) or leaf (4 types).

    Reads ALL the definition's ancillary keys (``flags`` of regex,
    ``min_coverage``/``min_similarity`` of coverage, ``min``/``max`` of attr_between), not only
    the type-key.
    """
    mapping = _require_mapping(raw, "token definition")
    if any(key in mapping for key in _CONDITION_KEYS):
        return _parse_condition(mapping)
    leaf_keys = [k for k in ("keyword", "regex", "coverage", "attr_between") if k in mapping]
    if len(leaf_keys) > 1:
        raise MatchingConfigError(f"a leaf token has exactly one type-key, got {sorted(leaf_keys)}")
    if "keyword" in mapping:
        return KeywordDefinition(phrase=str(mapping["keyword"]))
    if "regex" in mapping:
        flags = mapping.get("flags", "i")
        pattern = _expand_fragments(str(mapping["regex"]), fragments)
        return RegexDefinition(pattern=pattern, flags=str(flags))
    if "coverage" in mapping:
        _refuse_renamed_coverage_keys(mapping, f"token {token_name!r}")
        min_coverage = _optional_float(mapping, "min_coverage", f"token {token_name!r}")
        if min_coverage is None:
            raise MatchingConfigError("a coverage token must declare 'min_coverage'")
        min_similarity = _optional_float(mapping, "min_similarity", f"token {token_name!r}")
        return CoverageDefinition(
            reference=str(mapping["coverage"]),
            min_coverage=_require_unit_fraction(min_coverage, "coverage 'min_coverage'"),
            min_similarity=(
                0.85
                if min_similarity is None
                else _require_unit_fraction(min_similarity, "coverage 'min_similarity'")
            ),
        )
    if "attr_between" in mapping:
        attr = str(mapping["attr_between"])
        if attr in _RENAMED_ATTRS:
            raise MatchingConfigError(
                f"attr_between {attr!r} was renamed {_RENAMED_ATTRS[attr]!r}, "
                "rename it in matcher.yml"
            )
        if attr not in READERS_BY_ATTR:
            raise MatchingConfigError(
                f"unknown attr_between: {attr!r} (expected one of {sorted(READERS_BY_ATTR)})"
            )
        min_bound = _optional_float(mapping, "min", f"token {token_name!r}")
        max_bound = _optional_float(mapping, "max", f"token {token_name!r}")
        # Open bounds (min only / max only / none) are legitimate; only an explicit inverted
        # range min > max is an EMPTY range (rule mute forever) → fail-fast §8.4.
        if min_bound is not None and max_bound is not None and min_bound > max_bound:
            raise MatchingConfigError(
                f"attr_between {attr!r}: min ({min_bound}) > max ({max_bound}) (empty range)"
            )
        return AttributeBetweenDefinition(attr=attr, min_bound=min_bound, max_bound=max_bound)
    raise MatchingConfigError(f"unknown token shape: keys {sorted(mapping)}")


def _parse_rule(raw: Any) -> Rule:
    mapping = _require_mapping(raw, "rule")
    name = str(mapping.get("name", ""))
    if not name:
        raise MatchingConfigError(f"rule without 'name': {raw!r}")
    tier = mapping.get("tier")
    if tier not in TIERS:
        raise MatchingConfigError(
            f"unknown tier for rule {name!r}: {tier!r} (expected {sorted(TIERS)})"
        )
    if "scope" not in mapping:
        raise MatchingConfigError(
            f"rule {name!r} without 'scope' (expected one of {sorted(SCOPES)})"
        )
    scope = mapping["scope"]
    if scope not in SCOPES:
        raise MatchingConfigError(
            f"unknown scope for rule {name!r}: {scope!r} (expected {sorted(SCOPES)})"
        )
    present = [key for key in _CONDITION_KEYS if key in mapping]
    if not present:
        raise MatchingConfigError(f"rule {name!r} without a condition (all/any/not)")
    if len(present) != 1:
        raise MatchingConfigError(f"rule {name!r}: exactly one condition expected, got {present!r}")
    return Rule(name=name, tier=str(tier), scope=str(scope), condition=_parse_condition(mapping))


def parse_matcher_config(raw: dict[str, Any]) -> MatcherConfig:
    """Builds a validated (schema) :class:`MatcherConfig` from a parsed YAML dict."""
    fragments = _parse_fragments(raw.get("fragments", {}))
    tokens_raw = _require_mapping(raw.get("tokens", {}), "'tokens' section")
    tokens: dict[str, TokenDefinition] = {}
    for token_name, token_raw in tokens_raw.items():
        tokens[str(token_name)] = _parse_token_definition(str(token_name), token_raw, fragments)
    rules_raw = raw.get("rules", [])
    if not isinstance(rules_raw, list):
        raise MatchingConfigError(f"'rules' section: list expected, got {type(rules_raw).__name__}")
    rules = tuple(_parse_rule(rule_raw) for rule_raw in rules_raw)
    vetoes_raw = raw.get("vetoes", [])
    if not isinstance(vetoes_raw, list):
        raise MatchingConfigError(
            f"'vetoes' section: list expected, got {type(vetoes_raw).__name__}"
        )
    vetoes = tuple(str(name) for name in vetoes_raw)
    config = MatcherConfig(tokens=tokens, rules=rules, vetoes=vetoes)
    validate_config(config)
    return config


_DEFAULT_MAX_DEPTH = 32

# Probe target for the compile-check: provides season/seasonal_number/absolute_number/
# letter/title so that the interpolation of any RegexDefinition is testable at load time.
_PROBE_TARGET = TargetSegment(
    season=2,
    seasonal_number=11,
    absolute_number=62,
    letter="a",
    title="probe",
)


def _operand_token_names(operand: Operand) -> tuple[str, ...]:
    """Names of tokens directly referenced by an operand (str, TokenReference or inline)."""
    if isinstance(operand, str):
        return (operand,)
    if isinstance(operand, TokenReference):
        return (operand.name,)
    if isinstance(operand, NotDefinition):
        return _operand_token_names(operand.operand)
    # AllDefinition | AnyDefinition
    token_names: list[str] = []
    for child in operand.operands:
        token_names.extend(_operand_token_names(child))
    return tuple(token_names)


def _definition_token_names(token_definition: TokenDefinition) -> tuple[str, ...]:
    """Names of tokens directly referenced by a definition (empty for a leaf)."""
    if isinstance(token_definition, AllDefinition | AnyDefinition):
        token_names: list[str] = []
        for child in token_definition.operands:
            token_names.extend(_operand_token_names(child))
        return tuple(token_names)
    if isinstance(token_definition, NotDefinition):
        return _operand_token_names(token_definition.operand)
    return ()


def _operand_token_references(operand: Operand) -> tuple[TokenReference, ...]:
    """All TokenReferences (with their overrides) reachable from an operand."""
    if isinstance(operand, TokenReference):
        return (operand,)
    if isinstance(operand, NotDefinition):
        return _operand_token_references(operand.operand)
    if isinstance(operand, AllDefinition | AnyDefinition):
        token_references: list[TokenReference] = []
        for child in operand.operands:
            token_references.extend(_operand_token_references(child))
        return tuple(token_references)
    return ()  # str (bare name) -> no TokenReference


def _definition_token_references(token_definition: TokenDefinition) -> tuple[TokenReference, ...]:
    """All TokenReferences of a composite definition (empty for a leaf)."""
    if isinstance(token_definition, AllDefinition | AnyDefinition):
        token_references: list[TokenReference] = []
        for child in token_definition.operands:
            token_references.extend(_operand_token_references(child))
        return tuple(token_references)
    if isinstance(token_definition, NotDefinition):
        return _operand_token_references(token_definition.operand)
    return ()


def _check_overrides_only_on_coverage(config: MatcherConfig) -> None:
    """A min_coverage/min_similarity override is only legal on a coverage token (EBNF §8.3).

    Checked HERE (not at parsing) so as not to depend on the definition order: a forward
    reference to a coverage token must be accepted.
    """
    token_references: list[TokenReference] = []
    for token_definition in config.tokens.values():
        token_references.extend(_definition_token_references(token_definition))
    for rule in config.rules:
        token_references.extend(_operand_token_references(rule.condition))
    for token_reference in token_references:
        if (
            token_reference.min_coverage is not None or token_reference.min_similarity is not None
        ) and not isinstance(config.tokens.get(token_reference.name), CoverageDefinition):
            raise MatchingConfigError(
                "min_coverage/min_similarity override forbidden on non-coverage token "
                f"{token_reference.name!r}"
            )


def _check_references_exist(config: MatcherConfig) -> None:
    """Every reference (in a composite token OR a rule) must exist."""
    known = set(config.tokens)
    for token_definition in config.tokens.values():
        for token_name in _definition_token_names(token_definition):
            if token_name not in known:
                raise UnknownTokenError(f"reference to an unknown token: {token_name!r}")
    for rule in config.rules:
        for token_name in _operand_token_names(rule.condition):
            if token_name not in known:
                raise UnknownTokenError(
                    f"rule {rule.name!r}: reference to an unknown token: {token_name!r}"
                )


def _check_vetoes(config: MatcherConfig) -> None:
    """Every veto names a known token, at most once."""
    seen: set[str] = set()
    for name in config.vetoes:
        if name not in config.tokens:
            raise UnknownTokenError(f"veto references an unknown token: {name!r}")
        if name in seen:
            raise MatchingConfigError(f"duplicate veto: {name!r}")
        seen.add(name)


def _check_acyclic(config: MatcherConfig, max_depth: int) -> None:
    """Detects a cycle in the token->token graph and NAMES it (cf. spec §8.4).

    The ``len(stack) >= max_depth`` guard also bounds the recursion: a path deeper than
    ``max_depth`` is already a depth violation, raised cleanly here (avoids a Python
    ``RecursionError`` on a pathological chain).
    """
    graph = {
        name: _definition_token_names(token_definition)
        for name, token_definition in config.tokens.items()
    }
    visiting: set[str] = set()
    done: set[str] = set()
    stack: list[str] = []

    def walk(name: str) -> None:
        if name in done:
            return
        if name in visiting:
            cycle = stack[stack.index(name) :] + [name]
            raise CycleError(f"reference cycle: {' -> '.join(cycle)}")
        if len(stack) >= max_depth:
            tail = " -> ".join([*stack[-3:], name])
            raise DepthExceededError(f"resolution depth > {max_depth} (chain: … -> {tail})")
        visiting.add(name)
        stack.append(name)
        for token_name in graph.get(
            name, ()
        ):  # token_name exists (checked by _check_references_exist)
            walk(token_name)
        stack.pop()
        visiting.discard(name)
        done.add(name)

    for token_name in graph:
        walk(token_name)


def _max_resolution_depth(config: MatcherConfig) -> int:
    """Maximum depth of a token (leaf = 1). Assumes the graph is acyclic."""
    graph = {
        name: _definition_token_names(token_definition)
        for name, token_definition in config.tokens.items()
    }
    memo: dict[str, int] = {}

    def depth(name: str) -> int:
        if name in memo:
            return memo[name]
        token_names = graph.get(name, ())
        token_depth = (
            1 if not token_names else 1 + max(depth(token_name) for token_name in token_names)
        )
        memo[name] = token_depth
        return token_depth

    return max((depth(name) for name in graph), default=0)


def _check_regexes_compile(config: MatcherConfig) -> None:
    """Each RegexDefinition interpolates (known placeholders), compiles under ``re`` (cf. §8.4)."""
    for name, token_definition in config.tokens.items():
        if not isinstance(token_definition, RegexDefinition):
            continue
        if "segment" in PLACEHOLDER.findall(token_definition.pattern):
            raise MatchingConfigError(
                f"token {name!r}: placeholder '{{segment}}' was renamed '{{letter}}', "
                "rename it in matcher.yml"
            )
        try:
            pattern = interpolate(token_definition.pattern, _PROBE_TARGET)
        except InterpolationError as exc:
            raise MatchingConfigError(f"token {name!r}: invalid interpolation: {exc}") from exc
        if "i" in token_definition.flags:
            pattern = "(?i)" + pattern
        try:
            re.compile(pattern, re.ASCII)
        except re.error as exc:
            raise MatchingConfigError(f"token {name!r}: regex not compilable: {exc}") from exc


def validate_config(config: MatcherConfig, *, max_depth: int = _DEFAULT_MAX_DEPTH) -> None:
    """Validates the graph (references, DAG, depth) and the regexes (cf. spec §8.4).

    Raises :class:`UnknownTokenError`, :class:`CycleError`, :class:`DepthExceededError`
    or :class:`MatchingConfigError` (regex/interpolation). To be called after schema parsing.
    """
    _check_references_exist(config)
    _check_vetoes(config)
    _check_overrides_only_on_coverage(config)
    _check_acyclic(config, max_depth)
    depth = _max_resolution_depth(config)
    if depth > max_depth:
        raise DepthExceededError(
            f"resolution depth {depth} > max {max_depth} (default {_DEFAULT_MAX_DEPTH})"
        )
    _check_regexes_compile(config)


def parse_targets(raw: dict[str, Any]) -> tuple[TargetSegment, ...]:
    """Builds the :class:`TargetSegment`s from parsed ``targets.yaml`` (cf. spec §7)."""
    episodes = raw.get("episodes")
    if not isinstance(episodes, list):
        raise MatchingConfigError("'episodes' section: list expected")
    segments: list[TargetSegment] = []
    for episode in episodes:
        episode_mapping = _require_mapping(episode, "episode")
        season, seasonal_number, absolute_number = (
            _integer(_require_key(episode_mapping, key, "episode"), f"episode: key {key!r}")
            for key in ("season", "seasonal_number", "absolute_number")
        )
        segment_entries = episode_mapping.get("segments", [])
        for segment_entry in segment_entries:
            segment_mapping = _require_mapping(segment_entry, "segment")
            status = str(segment_mapping.get("status", LOST))
            if status not in TARGET_STATUSES:
                raise MatchingConfigError(
                    f"segment status {status!r} unknown (expected one of {sorted(TARGET_STATUSES)})"
                )
            segments.append(
                TargetSegment(
                    season=season,
                    seasonal_number=seasonal_number,
                    absolute_number=absolute_number,
                    letter=str(_require_key(segment_mapping, "letter", "segment")),
                    title=str(_require_key(segment_mapping, "title", "segment")),
                    status=status,
                )
            )
    parsed_segments = tuple(segments)
    seen: set[str] = set()
    for segment in parsed_segments:
        if segment.target_id in seen:
            raise MatchingConfigError(
                f"duplicate target_id: {segment.target_id!r}. Target segments must be "
                f"unique (note: the segment letter is uppercased by target_id, so 'a' and 'A' "
                f"collide). The evaluation engine depends on it (deterministic tie-break)."
            )
        seen.add(segment.target_id)
    return parsed_segments
