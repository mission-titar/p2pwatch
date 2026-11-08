"""``matcher.yml`` as written, read by pydantic, and the matcher config it builds."""

from pathlib import PurePath
from types import GenericAlias
from typing import Annotated, Any, Literal, NoReturn

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    create_model,
)
from pydantic_core import PydanticCustomError

from p2pwatch.adapters.driven.config.validation_problems import (
    TAG_MARK,
    renamed_key,
    validation_problems,
)
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.config import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_REGEX_FLAGS,
    AttributeBetweenDefinition,
    CoverageDefinition,
    KeywordDefinition,
    MatcherConfig,
    RegexDefinition,
    TokenDefinition,
)
from p2pwatch.domain.matching.validation import (
    MatchingConfigError,
    expand_fragments,
    fragment_problems,
    parse_condition,
    parse_rule,
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


# Every refusing field is built, since vulture reads a field nothing reads as dead code.
_COVERAGE_RENAMED: dict[str, Any] = {
    "min": (renamed_key("min_coverage", file_name=_FILE_NAME), None),
    "fuzz": (renamed_key("min_similarity", file_name=_FILE_NAME), None),
}
_CoverageSchema = create_model("_CoverageSchema", __base__=_CoverageKeys, **_COVERAGE_RENAMED)

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
_CONDITION = f"{TAG_MARK}condition"
_NO_SHAPE = f"{TAG_MARK}no_shape"


def _token_shape(token: object) -> str | None:
    """The tag of ``token``'s shape: a condition first, as the domain reads it, then its one leaf
    key; ``_NO_SHAPE`` for none or two, ``None`` for no mapping."""
    if not isinstance(token, dict):
        return None
    if any(key in token for key in _CONDITION_KEYS):
        return _CONDITION
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


# Typed Any, since mypy refuses a variable schema in a type.
_TOKEN_SCHEMA: Any = Annotated[
    Annotated[_KeywordSchema, Tag(f"{TAG_MARK}keyword")]
    | Annotated[_RegexSchema, Tag(f"{TAG_MARK}regex")]
    | Annotated[_CoverageSchema, Tag(f"{TAG_MARK}coverage")]
    | Annotated[
        _AttributeBetweenSchema,
        AfterValidator(_refuse_an_empty_range),
        Tag(f"{TAG_MARK}attr_between"),
    ]
    # Read by the domain's parse until it is modelled.
    | Annotated[dict[str, Any], Tag(_CONDITION)]
    | Annotated[dict[str, Any], BeforeValidator(_refuse_the_shape), Tag(_NO_SHAPE)],
    Discriminator(
        _token_shape,
        custom_error_type="token_type",
        custom_error_message="Input should be a valid dictionary",
    ),
]


_TokenKeys = (
    _KeywordSchema | _RegexSchema | _CoverageKeys | _AttributeBetweenSchema | dict[str, Any]
)


class _MatcherKeys(BaseModel, extra="forbid", strict=True):
    fragments: dict[str, _Pattern] = Field(default_factory=dict)
    # Its schema in MatcherConfigSchema, whose coverage token adds the refusing keys.
    tokens: dict[str, _TokenKeys] = Field(default_factory=dict)
    # Read by the domain's parse until they are modelled.
    rules: list[Any] = Field(default_factory=list)
    vetoes: list[str] = Field(default_factory=list)


_TOKENS: dict[str, Any] = {
    # dict[str, _TOKEN_SCHEMA], which mypy refuses since the schema is a variable.
    "tokens": (GenericAlias(dict, (str, _TOKEN_SCHEMA)), Field(default_factory=dict))
}
MatcherConfigSchema = create_model("MatcherConfigSchema", __base__=_MatcherKeys, **_TOKENS)


def matcher_config_from_document(document: dict[str, Any], *, file_path: PurePath) -> MatcherConfig:
    """``document``'s matcher config; ``InvalidConfigError`` with every problem of its fragments
    and tokens, or once they hold, its first other problem."""
    try:
        schema = MatcherConfigSchema.model_validate(document)
    except ValidationError as error:
        raise InvalidConfigError(validation_problems(error, file_path=file_path)) from error
    if problems := fragment_problems(schema.fragments, file_path=file_path):
        raise InvalidConfigError(problems)
    try:
        matcher_config = MatcherConfig(
            tokens={
                name: _token_definition(token, fragments=schema.fragments)
                for name, token in schema.tokens.items()
            },
            rules=tuple(parse_rule(rule) for rule in schema.rules),
            vetoes=tuple(schema.vetoes),
        )
        validate_config(matcher_config)
    except MatchingConfigError as error:
        problem = ConfigProblem(file_path=file_path, key=None, message=str(error))
        raise InvalidConfigError((problem,)) from error
    return matcher_config


def _token_definition(token: _TokenKeys, *, fragments: dict[str, str]) -> TokenDefinition:
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
            return parse_condition(token)
