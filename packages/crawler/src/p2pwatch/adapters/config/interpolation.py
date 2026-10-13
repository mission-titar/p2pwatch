"""${NAME} interpolation (substring, fail-fast) — env I/O, so in the adapter (spec D1/D3)."""

import re
from collections.abc import Mapping

from p2pwatch.adapters.config.errors import ConfigError

_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate(value: str, env: Mapping[str, str], field: str) -> str:
    """Substitute each ``${NAME}`` in ``value`` with ``env[NAME]``.

    Missing variable ⇒ ``ConfigError`` prefixed by ``field`` (spec D1).
    No match ⇒ ``value`` returned as-is (lone ``$`` are left untouched).
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ConfigError(f"{field}: environment variable {name!r} referenced but not set")
        return env[name]

    return _PATTERN.sub(_replace, value)
