"""${NAME} interpolation (substring): env I/O, so in the adapter (spec D1/D3)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.value_bounds import require_well_formed_text

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(kw_only=True, frozen=True)
class InterpolatedDocument:
    """A document with its ``${NAME}`` resolved, those in ``problems`` left as written."""

    document: dict[str, Any]
    problems: tuple[ConfigProblem, ...]


def interpolate_document(
    document: dict[str, Any], *, env: Mapping[str, str], file_path: PurePath
) -> InterpolatedDocument:
    """``document`` with each ``${NAME}`` of every string value replaced by ``env[NAME]``, every
    unset or ill-formed variable a problem of ``file_path``.

    The keys are left as they are: they name the schema. A lone ``$`` is left untouched.
    """
    interpolation = _Interpolation(env=env, file_path=file_path)
    resolved = {
        key: interpolation.subtree(subtree, key_path=str(key)) for key, subtree in document.items()
    }
    return InterpolatedDocument(document=resolved, problems=tuple(interpolation.problems))


class _Interpolation:
    def __init__(self, *, env: Mapping[str, str], file_path: PurePath) -> None:
        self._env = env
        self._file_path = file_path
        self.problems: list[ConfigProblem] = []

    def subtree(self, subtree: Any, *, key_path: str) -> Any:
        match subtree:
            case str():
                return _ENV_REFERENCE.sub(
                    lambda match: self._value(match, key_path=key_path), subtree
                )
            case dict():
                return {
                    key: self.subtree(child, key_path=f"{key_path}.{key}")
                    for key, child in subtree.items()
                }
            case list():
                return [
                    self.subtree(child, key_path=f"{key_path}[{index}]")
                    for index, child in enumerate(subtree)
                ]
            case _:
                return subtree

    def _value(self, match: re.Match[str], *, key_path: str) -> str:
        """The variable ``match`` references, or ``match`` as written with its problem kept."""
        name = match.group(1)
        if name not in self._env:
            return self._unresolved(
                match,
                key_path=key_path,
                message=f"environment variable {name!r} referenced but not set",
            )
        try:
            require_well_formed_text(self._env[name], error_label=f"environment variable {name!r}")
        except ValueError as error:
            return self._unresolved(match, key_path=key_path, message=str(error))
        return self._env[name]

    def _unresolved(self, match: re.Match[str], *, key_path: str, message: str) -> str:
        self.problems.append(
            ConfigProblem(file_path=self._file_path, key=key_path, message=message)
        )
        return match.group(0)
