"""${NAME} interpolation (substring, fail-fast): env I/O, so in the adapter (spec D1/D3)."""

import re
from collections.abc import Mapping

from p2pwatch.adapters.driven.config.errors import ConfigError

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate(value: str, env: Mapping[str, str], error_label: str) -> str:
    """Substitute each ``${NAME}`` in ``value`` with ``env[NAME]``.

    Missing variable ⇒ ``ConfigError`` prefixed by ``error_label`` (spec D1).
    No match ⇒ ``value`` returned as-is (lone ``$`` are left untouched).
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise ConfigError(
                f"{error_label}: environment variable {name!r} referenced but not set"
            )
        return env[name]

    return _ENV_REFERENCE.sub(_replace, value)
