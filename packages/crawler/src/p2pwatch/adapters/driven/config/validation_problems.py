"""A pydantic ``ValidationError`` as its file's ``ConfigProblem``s, and our 4.x key refusals."""

from pathlib import PurePath
from typing import Annotated, Any, NoReturn

from pydantic import AfterValidator, ValidationError
from pydantic_core import ErrorDetails, PydanticCustomError

from p2pwatch.domain.config_problem import ConfigProblem

_REPLACED = "config_key_replaced"

# Begins a tagged union's tag, which pydantic puts in an error's location and no key is named.
TAG_MARK = "~"


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
    error: ValidationError, *, file_path: PurePath
) -> tuple[ConfigProblem, ...]:
    """Each of ``error``'s errors as a problem of ``file_path``, never with the value received
    (a resolved ``${NAME}`` may be a secret); a moved or renamed key's new place is not required
    beside it."""
    details = error.errors(include_url=False, include_input=False)
    new_places = {
        (*detail["loc"][:-1], *detail["ctx"]["new_key"].split("."))
        for detail in details
        if detail["type"] == _REPLACED
    }
    return tuple(
        ConfigProblem(file_path=file_path, key=_key_path(detail["loc"]), message=_message(detail))
        for detail in details
        if not (detail["type"] == "missing" and detail["loc"] in new_places)
    )


def _key_path(location: tuple[int | str, ...]) -> str:
    keys = (part for part in location if not str(part).startswith(TAG_MARK))
    parts = (f"[{part}]" if isinstance(part, int) else f".{part}" for part in keys)
    return "".join(parts).removeprefix(".")


def _message(detail: ErrorDetails) -> str:
    # pydantic's names the schema's class, which the operator never wrote.
    return "Input should be a valid dictionary" if detail["type"] == "model_type" else detail["msg"]
