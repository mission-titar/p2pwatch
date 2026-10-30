"""Adapter: reads a YAML file into Python structures (cf. spec §4 I/O boundary).

The ONLY module in the project that imports ``yaml`` and touches the filesystem for
config. Checks the file's form only: UTF-8, YAML, a mapping at its root, and every text valid
UTF-8; the substance is the domain's (``catalog_matching.domain.validation``).
"""

from pathlib import Path
from typing import Any

import yaml

from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.value_bounds import require_well_formed_text


def load_yaml(path: Path) -> dict[str, Any]:
    """Reads ``path`` and returns its root (a mapping) parsed by ``yaml.safe_load``.

    ``safe_load`` parses ISO dates into ``datetime.date`` and instantiates no arbitrary
    Python object (no unsafe ``yaml.load``). A file absent, unreadable, not UTF-8, not YAML,
    whose root is no mapping (an empty file's is ``None``) or holding a text that is not valid
    UTF-8, a key's included (an escaped surrogate, ``"\\ud800"``), raises
    :class:`BrokenInputError`.
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
    try:
        _require_well_formed_texts(root, key_path="")
    except ValueError as error:
        raise BrokenInputError(f"{path}: {error}") from error
    return root


def _require_well_formed_texts(node: Any, *, key_path: str) -> None:
    """Refuses a text of ``node``, a key's included, that is not valid UTF-8, naming its path."""
    match node:
        case str():
            require_well_formed_text(node, error_label=key_path)
        case dict():
            for key, child in node.items():
                child_path = f"{key_path}.{key}" if key_path else str(key)
                _require_well_formed_texts(key, key_path=child_path)
                _require_well_formed_texts(child, key_path=child_path)
        case list():
            for index, child in enumerate(node):
                _require_well_formed_texts(child, key_path=f"{key_path}[{index}]")


def _on_one_line(error: yaml.YAMLError) -> str:
    """``error``'s text on one line, without the snippet of the text its marks quote."""
    return " ".join(line.strip() for line in str(error).splitlines() if not line.startswith("    "))
