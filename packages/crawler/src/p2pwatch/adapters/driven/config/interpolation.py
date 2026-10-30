"""${NAME} interpolation (substring, fail-fast): env I/O, so in the adapter (spec D1/D3)."""

import re
from collections.abc import Mapping
from typing import Any

from p2pwatch.domain.invalid_config import InvalidConfigError

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate_document(document: dict[str, Any], *, env: Mapping[str, str]) -> dict[str, Any]:
    """``document`` with each ``${NAME}`` of every string value replaced by ``env[NAME]``.

    The keys are left as they are: they name the schema. A lone ``$`` is left untouched.
    """
    return {
        key: _interpolate_node(node, env=env, key_path=str(key)) for key, node in document.items()
    }


def _interpolate_node(node: Any, *, env: Mapping[str, str], key_path: str) -> Any:
    match node:
        case str():
            return _interpolate_text(node, env=env, key_path=key_path)
        case dict():
            return {
                key: _interpolate_node(child, env=env, key_path=f"{key_path}.{key}")
                for key, child in node.items()
            }
        case list():
            return [
                _interpolate_node(child, env=env, key_path=f"{key_path}[{index}]")
                for index, child in enumerate(node)
            ]
        case _:
            return node


def _interpolate_text(text: str, *, env: Mapping[str, str], key_path: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise InvalidConfigError(
                key_path, message=f"environment variable {name!r} referenced but not set"
            )
        return env[name]

    return _ENV_REFERENCE.sub(_replace, text)
