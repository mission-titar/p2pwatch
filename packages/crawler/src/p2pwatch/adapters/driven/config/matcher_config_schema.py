"""``matcher.yml`` as written, read by pydantic, and the matcher config it builds."""

from pathlib import PurePath
from typing import Annotated, Any, Literal, NoReturn

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Discriminator,
    Field,
    GetPydanticSchema,
    Tag,
    ValidationError,
    create_model,
)
from pydantic_core import PydanticCustomError

from p2pwatch.adapters.driven.config.validation_problems import (
    TAG_MARK,
    refuse_control_character,
    renamed_key,
    validation_problems,
)
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.config import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_REGEX_FLAGS,
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
    Scope,
    TokenDefinition,
    TokenReference,
)
from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.validation import (
    MatchingConfigError,
    expand_fragments,
    fragment_problems,
    validate_config,
)

_FILE_NAME = "matcher.yml"


def _refuse_segment_placeholder(pattern: str) -> str:
    if "{segment}" in pattern:
        raise PydanticCustomError(
            "config_value_renamed",
            f"placeholder '{{segment}}' was renamed '{{letter}}', rename it in {_FILE_NAME}",
        )
    return pattern


_Pattern = Annotated[str, AfterValidator(_refuse_segment_placeholder)]
_Fraction = Annotated[float, Field(ge=0, le=1)]


class _KeywordSchema(BaseModel, extra="forbid", strict=True):
    keyword: str


class _RegexSchema(BaseModel, extra="forbid", strict=True):
    regex: _Pattern
    flags: str = DEFAULT_REGEX_FLAGS


class _CoverageKeys(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    coverage: str
    min_coverage: _Fraction
    min_similarity: _Fraction = DEFAULT_MIN_SIMILARITY


class _TokenReferenceKeys(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    token: str
    min_coverage: _Fraction | None = None
    min_similarity: _Fraction | None = None


# Every refusing field is built, since vulture reads a field nothing reads as dead code.
_COVERAGE_RENAMED: dict[str, Any] = {
    "min": (renamed_key("min_coverage", file_name=_FILE_NAME), None),
    "fuzz": (renamed_key("min_similarity", file_name=_FILE_NAME), None),
}
_CoverageSchema = create_model("_CoverageSchema", __base__=_CoverageKeys, **_COVERAGE_RENAMED)
_TokenReferenceSchema = create_model(
    "_TokenReferenceSchema", __base__=_TokenReferenceKeys, **_COVERAGE_RENAMED
)
# mypy reads the keys' class, which a built schema extends: pydantic validates by the schema.
_AS_COVERAGE_SCHEMA = GetPydanticSchema(lambda _source, handler: handler(_CoverageSchema))
_AS_REFERENCE_SCHEMA = GetPydanticSchema(lambda _source, handler: handler(_TokenReferenceSchema))

_RENAMED_ATTRIBUTES = {"size_mb": "size_mib", "duration_sec": "duration_seconds"}


def _refuse_renamed_attribute(attribute: object) -> object:
    if isinstance(attribute, str) and attribute in _RENAMED_ATTRIBUTES:
        raise PydanticCustomError(
            "config_value_renamed",
            f"'{attribute}' was renamed '{_RENAMED_ATTRIBUTES[attribute]}', "
            f"rename it in {_FILE_NAME}",
        )
    return attribute


class _AttributeBetweenSchema(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    # The engine's READERS_BY_ATTR, which its own tests compare.
    attr_between: Annotated[
        Literal["size_mib", "duration_seconds", "bitrate_kbps"],
        BeforeValidator(_refuse_renamed_attribute),
    ]
    min: float | None = None
    max: float | None = None


def _refuse_an_empty_range(token: _AttributeBetweenSchema) -> _AttributeBetweenSchema:
    if token.min is not None and token.max is not None and token.min > token.max:
        raise PydanticCustomError("empty_range", "'min' is above 'max', an empty range")
    return token


_CONDITION_KEYS = ("all", "any", "not")
_LEAF_KEYS = ("keyword", "regex", "coverage", "attr_between")
_NO_SHAPE = f"{TAG_MARK}no_shape"


def _token_shape(token: object) -> str | None:
    """The tag of ``token``'s shape: a condition first, as 4.x read it, then its one leaf key;
    ``_NO_SHAPE`` for none or two, ``None`` for no mapping."""
    if not isinstance(token, dict):
        return None
    if condition := _condition_shape(token):
        return condition
    leaf_keys = [key for key in _LEAF_KEYS if key in token]
    return f"{TAG_MARK}{leaf_keys[0]}" if len(leaf_keys) == 1 else _NO_SHAPE


def _refuse_the_shape(token: dict[Any, Any]) -> NoReturn:
    # The discriminator cannot raise: its error would drop every other problem of the document.
    if leaf_keys := sorted(key for key in _LEAF_KEYS if key in token):
        raise PydanticCustomError(
            "token_shape",
            "a leaf token has exactly one type-key, got {keys}",
            {"keys": leaf_keys},
        )
    raise PydanticCustomError(
        "token_shape",
        "unknown token shape: keys {keys}",
        {"keys": sorted(str(key) for key in token)},
    )


_ALL = f"{TAG_MARK}all"
_ANY = f"{TAG_MARK}any"
_NOT = f"{TAG_MARK}not"
_NAME = f"{TAG_MARK}name"
_REFERENCE = f"{TAG_MARK}reference"
_NOT_ONE_CONDITION = f"{TAG_MARK}not_one_condition"


def _condition_shape(mapping: dict[Any, Any]) -> str | None:
    """The tag of ``mapping``'s condition key, ``_NOT_ONE_CONDITION`` for two, ``None`` for none."""
    present = [key for key in _CONDITION_KEYS if key in mapping]
    if not present:
        return None
    return f"{TAG_MARK}{present[0]}" if len(present) == 1 else _NOT_ONE_CONDITION


def _rule_shape(rule: object) -> str | None:
    if not isinstance(rule, dict):
        return None
    return _condition_shape(rule) or _NOT_ONE_CONDITION


def _operand_shape(operand: object) -> str | None:
    """A token name, a condition, else a ``{token: ...}`` reference; ``None`` for no string
    and no mapping."""
    if isinstance(operand, str):
        return _NAME
    if not isinstance(operand, dict):
        return None
    return _condition_shape(operand) or _REFERENCE


def _refuse_the_conditions(mapping: dict[Any, Any]) -> NoReturn:
    raise PydanticCustomError(
        "condition_shape",
        "exactly one condition (all/any/not) expected, got {keys}",
        {"keys": [key for key in _CONDITION_KEYS if key in mapping]},
    )


# Any, since its validator refuses every value: pydantic has no schema for Never.
_NotOneCondition = Annotated[Any, BeforeValidator(_refuse_the_conditions), Tag(_NOT_ONE_CONDITION)]


# Lazy, so that the conditions below can hold it.
type _Operand = Annotated[
    Annotated[str, Tag(_NAME)]
    | Annotated[_TokenReferenceKeys, _AS_REFERENCE_SCHEMA, Tag(_REFERENCE)]
    | Annotated[_AllSchema, Tag(_ALL)]
    | Annotated[_AnySchema, Tag(_ANY)]
    | Annotated[_NotSchema, Tag(_NOT)]
    | _NotOneCondition,
    Discriminator(
        _operand_shape,
        custom_error_type="operand_type",
        custom_error_message="Input should be a valid string or dictionary",
    ),
]


class _AllSchema(BaseModel, extra="forbid", strict=True):
    operands: list[_Operand] = Field(alias="all", min_length=1)


class _AnySchema(BaseModel, extra="forbid", strict=True):
    operands: list[_Operand] = Field(alias="any", min_length=1)


class _NotSchema(BaseModel, extra="forbid", strict=True):
    operand: _Operand = Field(alias="not")


class _RuleKeys(BaseModel, extra="forbid", strict=True):
    name: Annotated[str, Field(min_length=1), AfterValidator(refuse_control_character)]
    # DecisionTier's values, which its own tests compare: strict, pydantic refuses a str for it.
    tier: Literal["catalog", "notify", "download"]
    scope: Scope


class _AllRule(_AllSchema, _RuleKeys):
    """A rule whose condition is ``all``."""


class _AnyRule(_AnySchema, _RuleKeys):
    """A rule whose condition is ``any``."""


class _NotRule(_NotSchema, _RuleKeys):
    """A rule whose condition is ``not``."""


type _Rule = Annotated[
    Annotated[_AllRule, Tag(_ALL)]
    | Annotated[_AnyRule, Tag(_ANY)]
    | Annotated[_NotRule, Tag(_NOT)]
    | _NotOneCondition,
    Discriminator(
        _rule_shape,
        custom_error_type="rule_type",
        custom_error_message="Input should be a valid dictionary",
    ),
]


type _Token = Annotated[
    Annotated[_KeywordSchema, Tag(f"{TAG_MARK}keyword")]
    | Annotated[_RegexSchema, Tag(f"{TAG_MARK}regex")]
    | Annotated[_CoverageKeys, _AS_COVERAGE_SCHEMA, Tag(f"{TAG_MARK}coverage")]
    | Annotated[
        _AttributeBetweenSchema,
        AfterValidator(_refuse_an_empty_range),
        Tag(f"{TAG_MARK}attr_between"),
    ]
    | Annotated[_AllSchema, Tag(_ALL)]
    | Annotated[_AnySchema, Tag(_ANY)]
    | Annotated[_NotSchema, Tag(_NOT)]
    | _NotOneCondition
    | Annotated[Any, BeforeValidator(_refuse_the_shape), Tag(_NO_SHAPE)],
    Discriminator(
        _token_shape,
        custom_error_type="token_type",
        custom_error_message="Input should be a valid dictionary",
    ),
]


class MatcherConfigSchema(BaseModel, extra="forbid", strict=True):
    fragments: dict[str, _Pattern] = Field(default_factory=dict)
    tokens: dict[str, _Token] = Field(default_factory=dict)
    rules: list[_Rule] = Field(default_factory=list)
    vetoes: list[str] = Field(default_factory=list)


def matcher_config_from_document(document: dict[str, Any], *, file_path: PurePath) -> MatcherConfig:
    """``document``'s matcher config; ``InvalidConfigError`` with every problem of its values,
    or once they hold, its first other problem."""
    try:
        schema = MatcherConfigSchema.model_validate(document)
    except ValidationError as error:
        raise InvalidConfigError(validation_problems(error, file_path=file_path)) from error
    if problems := fragment_problems(schema.fragments, file_path=file_path):
        raise InvalidConfigError(problems)
    matcher_config = MatcherConfig(
        tokens={
            name: _token_definition(token, fragments=schema.fragments)
            for name, token in schema.tokens.items()
        },
        rules=tuple(_rule(rule) for rule in schema.rules),
        vetoes=tuple(schema.vetoes),
    )
    try:
        validate_config(matcher_config)
    except MatchingConfigError as error:
        problem = ConfigProblem(file_path=file_path, key=None, message=str(error))
        raise InvalidConfigError((problem,)) from error
    return matcher_config


def _token_definition(token: _Token, *, fragments: dict[str, str]) -> TokenDefinition:
    match token:
        case _KeywordSchema():
            return KeywordDefinition(phrase=token.keyword)
        case _RegexSchema():
            pattern = expand_fragments(token.regex, fragments=fragments)
            return RegexDefinition(pattern=pattern, flags=token.flags)
        case _CoverageKeys():
            return CoverageDefinition(
                reference=token.coverage,
                min_coverage=token.min_coverage,
                min_similarity=token.min_similarity,
            )
        case _AttributeBetweenSchema():
            return AttributeBetweenDefinition(
                attr=token.attr_between, min_bound=token.min, max_bound=token.max
            )
        case _:
            return _condition(token)


def _rule(rule: _Rule) -> Rule:
    return Rule(
        name=rule.name, tier=DecisionTier(rule.tier), scope=rule.scope, condition=_condition(rule)
    )


def _condition(condition: _AllSchema | _AnySchema | _NotSchema) -> Condition:
    match condition:
        case _AllSchema():
            return AllDefinition(
                operands=tuple(_operand(operand) for operand in condition.operands)
            )
        case _AnySchema():
            return AnyDefinition(
                operands=tuple(_operand(operand) for operand in condition.operands)
            )
        case _:
            return NotDefinition(operand=_operand(condition.operand))


def _operand(operand: _Operand) -> Operand:
    match operand:
        case str():
            return operand
        case _TokenReferenceKeys():
            return TokenReference(
                name=operand.token,
                min_coverage=operand.min_coverage,
                min_similarity=operand.min_similarity,
            )
        case _:
            return _condition(operand)
