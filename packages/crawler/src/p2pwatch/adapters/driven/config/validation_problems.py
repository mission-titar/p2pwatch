"""A pydantic ``ValidationError`` as its file's ``ConfigProblem``s, our 4.x key refusals and
the identifiers' one."""

from pathlib import PurePath
from typing import Annotated, Any, NoReturn

from pydantic import AfterValidator, BaseModel, ValidationError
from pydantic_core import ErrorDetails, PydanticCustomError

from p2pwatch.domain.config_problem import ConfigProblem, key_path
from p2pwatch.domain.matching.validation import has_control_character

_REPLACED = "config_key_replaced"
# Ends the location of an error on a mapping's key, rather than on its value.
_KEY_MARK = "[key]"

# Begins a tagged union's tag, which pydantic puts in an error's location and no key is named.
TAG_MARK = "~"


class StrictSchema(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    """The base of every schema: a key nothing reads refused, no value converted, no infinity."""


def refuse_control_character(text: str) -> str:
    """``text``, refused when it holds a control character, as no identifier does: a target's
    letter, a rule's name."""
    if has_control_character(text):
        raise PydanticCustomError("control_character", "holds a control character")
    return text


def removed_key(file_name: str) -> object:
    """The type of a key nothing reads since 4.x: present, even empty, it is refused."""

    def refuse(_: object) -> NoReturn:
        raise PydanticCustomError("config_key_removed", f"was removed, delete it from {file_name}")

    return Annotated[Any, AfterValidator(refuse)]


def moved_key(new_key: str, *, file_name: str) -> object:
    """The type of a key 4.x read where ``new_key``, its path from the same mapping, is read now."""
    return _replaced_key(new_key, message=f"moved to '{new_key}', move it in {file_name}")


def renamed_key(new_name: str, *, file_name: str) -> object:
    """The type of a key 4.x read in the same mapping as ``new_name``, its name now."""
    return _replaced_key(new_name, message=f"was renamed '{new_name}', rename it in {file_name}")


def _replaced_key(new_key: str, *, message: str) -> object:
    def refuse(_: object) -> NoReturn:
        raise PydanticCustomError(_REPLACED, message, {"new_key": new_key})

    return Annotated[Any, AfterValidator(refuse)]


def validation_problems(
    error: ValidationError, *, document: object, file_path: PurePath
) -> tuple[ConfigProblem, ...]:
    """Each of ``error``'s errors on ``document`` as a problem of ``file_path``, never with the
    value received (a resolved ``${NAME}`` may be a secret); a moved or renamed key's new place
    is not required beside it."""
    details = error.errors(include_url=False, include_input=False)
    new_places = {
        (*detail["loc"][:-1], *detail["ctx"]["new_key"].split("."))
        for detail in details
        if detail["type"] == _REPLACED
    }
    return tuple(
        ConfigProblem(
            file_path=file_path,
            key=_key_path(detail["loc"], document=document),
            message=_message(detail),
        )
        for detail in details
        if not (detail["type"] == "missing" and detail["loc"] in new_places)
    )


def _key_path(location: tuple[int | str, ...], *, document: object) -> str:
    """``location``'s key path, walked through ``document``: an integer is an index in a list
    and a key in a mapping, which YAML lets be no string."""
    parts: list[str | int] = []
    value = document
    for part in location:
        if part == _KEY_MARK or str(part).startswith(TAG_MARK):
            continue
        if isinstance(value, list) and isinstance(part, int):
            parts.append(part)
            value = value[part]
        else:
            parts.append(str(part))
            value = value.get(part) if isinstance(value, dict) else None
    return key_path(*parts)


def _message(detail: ErrorDetails) -> str:
    if detail["loc"][-1] == _KEY_MARK:
        # pydantic's reads "Input" for a key too.
        return detail["msg"].replace("Input", "Key", 1)
    # pydantic's names the schema's class, which the operator never wrote.
    return "Input should be a valid dictionary" if detail["type"] == "model_type" else detail["msg"]
