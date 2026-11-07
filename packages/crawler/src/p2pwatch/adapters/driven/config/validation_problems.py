"""A pydantic ``ValidationError`` as its file's ``ConfigProblem``s, and our 4.x key refusals."""

from pathlib import PurePath
from typing import Annotated, Any, NoReturn

from pydantic import AfterValidator, ValidationError
from pydantic_core import PydanticCustomError

from p2pwatch.domain.config_problem import ConfigProblem


def removed_key(file_name: str) -> object:
    """The type of a key nothing reads since 4.x: present, even empty, it is refused."""

    def refuse(_: object) -> NoReturn:
        raise PydanticCustomError("config_key_removed", f"was removed, delete it from {file_name}")

    return Annotated[Any, AfterValidator(refuse)]


def moved_key(new_key: str, *, file_name: str) -> object:
    """The type of a key 4.x read where ``new_key`` is read now."""

    def refuse(_: object) -> NoReturn:
        raise PydanticCustomError(
            "config_key_moved", f"moved to '{new_key}', move it in {file_name}"
        )

    return Annotated[Any, AfterValidator(refuse)]


def validation_problems(
    error: ValidationError, *, file_path: PurePath
) -> tuple[ConfigProblem, ...]:
    """Each of ``error``'s errors as a problem of ``file_path``, never with the value received:
    a resolved ``${NAME}`` may be a secret."""
    return tuple(
        ConfigProblem(file_path=file_path, key=_key_path(detail["loc"]), message=detail["msg"])
        for detail in error.errors(include_url=False, include_input=False)
    )


def _key_path(location: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in location)
