"""Adapter: reads a YAML file into Python structures (cf. spec §4 I/O boundary).

The ONLY module in the project that imports ``yaml`` and touches the filesystem for
config. Does NOT validate the substance (schema/graph/RE2): that's the domain's job
(``catalog_matching.domain.validation``). Minimal guardrail: the root must be a mapping.
"""

from pathlib import Path
from typing import Any

import yaml

from p2pwatch.domain.broken_input_error import BrokenInputError


def load_yaml(path: Path) -> dict[str, Any]:
    """Reads ``path`` and returns its root (a mapping) parsed by ``yaml.safe_load``.

    ``safe_load`` parses ISO dates into ``datetime.date`` and instantiates no arbitrary
    Python object (no unsafe ``yaml.load``). A file absent, unreadable, not UTF-8, not YAML or
    whose root is no mapping (an empty file's is ``None``) raises :class:`BrokenInputError`.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise BrokenInputError(f"{path}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise BrokenInputError(f"{path}: not UTF-8") from error
    try:
        root = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise BrokenInputError(f"{path}: invalid YAML: {_on_one_line(error)}") from error
    if not isinstance(root, dict):
        raise BrokenInputError(f"{path}: mapping expected at its root, got {type(root).__name__}")
    return root


def _on_one_line(error: yaml.YAMLError) -> str:
    """``error``'s text on one line, without the snippet of the text its marks quote."""
    return " ".join(line.strip() for line in str(error).splitlines() if not line.startswith("    "))
