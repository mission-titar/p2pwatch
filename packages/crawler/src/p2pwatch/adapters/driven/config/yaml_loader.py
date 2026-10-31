"""Adapter: the ONLY module reading a config file and importing ``yaml``; it checks the form."""

from pathlib import Path
from typing import Any

import yaml

from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.value_bounds import require_well_formed_text


def load_yaml(path: Path) -> dict[str, Any]:
    """``path``'s root mapping, by ``yaml.safe_load``. Raises ``BrokenInputError`` on a file absent,
    unreadable, not UTF-8 nor YAML, with no mapping at its root, an alias cycle or a surrogate."""
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
        _require_well_formed_tree(root, key_path="", enclosing_ids=frozenset())
    except ValueError as error:
        raise BrokenInputError(f"{path}: {error}") from error
    return root


def _require_well_formed_tree(
    subtree: Any, *, key_path: str, enclosing_ids: frozenset[int]
) -> None:
    """Refuses in ``subtree`` a text that is not valid UTF-8, a key's included, and an alias of a
    value enclosing it (``enclosing_ids``), which ``safe_load`` builds as a cycle."""
    match subtree:
        case str():
            require_well_formed_text(subtree, error_label=key_path)
        case dict() | list() if id(subtree) in enclosing_ids:
            raise ValueError(f"{key_path} refers to a value that holds it")
        case dict():
            child_enclosing_ids = enclosing_ids | {id(subtree)}
            for key, child in subtree.items():
                key_text = _printable_key(key)
                child_path = f"{key_path}.{key_text}" if key_path else key_text
                _require_well_formed_tree(key, key_path=child_path, enclosing_ids=enclosing_ids)
                _require_well_formed_tree(
                    child, key_path=child_path, enclosing_ids=child_enclosing_ids
                )
        case list():
            child_enclosing_ids = enclosing_ids | {id(subtree)}
            for index, child in enumerate(subtree):
                _require_well_formed_tree(
                    child, key_path=f"{key_path}[{index}]", enclosing_ids=child_enclosing_ids
                )


def _printable_key(key: object) -> str:
    """``key`` as text, each character ``isprintable`` refuses escaped, so an error can name it."""
    return "".join(
        character if character.isprintable() else character.encode("unicode_escape").decode()
        for character in str(key)
    )


def _on_one_line(error: yaml.YAMLError) -> str:
    """``error``'s text on one line, without the snippet of the text its marks quote."""
    return " ".join(line.strip() for line in str(error).splitlines() if not line.startswith("    "))
