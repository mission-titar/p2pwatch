"""Adapter: the ONLY module reading a config file and importing ``yaml``; it checks the form."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.value_bounds import require_well_formed_text

_MERGE_TAG = "tag:yaml.org,2002:merge"


@dataclass(kw_only=True, frozen=True)
class LoadedDocument:
    """A file's root mapping, a key written twice holding its latest value, each such key a
    problem in ``problems``."""

    document: dict[str, Any]
    problems: tuple[ConfigProblem, ...]


def load_yaml(path: Path) -> LoadedDocument:
    """``path``'s root mapping, as ``yaml.safe_load`` builds it; ``BrokenInputError`` on a file
    absent, unreadable, not UTF-8 nor YAML, with no root mapping, an alias cycle or a surrogate."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise BrokenInputError(path, reason=str(error.strerror)) from error
    except UnicodeDecodeError as error:
        raise BrokenInputError(path, reason="not UTF-8") from error
    loader = _RecordingLoader(text, file_path=path)
    try:
        root = loader.get_single_data()
    except yaml.YAMLError as error:
        raise BrokenInputError(path, reason=f"invalid YAML: {_on_one_line(error)}") from error
    finally:
        loader.dispose()
    if not isinstance(root, dict):
        raise BrokenInputError(
            path, reason=f"mapping expected at its root, got {type(root).__name__}"
        )
    try:
        _require_well_formed_tree(root, key_path="", enclosing_ids=frozenset())
    except ValueError as error:
        raise BrokenInputError(path, reason=str(error)) from error
    return LoadedDocument(document=root, problems=tuple(loader.keys_written_twice))


class _RecordingLoader(yaml.SafeLoader):
    """``SafeLoader`` recording each mapping key written twice, which the mapping it builds keeps
    once, holding the latest value."""

    def __init__(self, text: str, *, file_path: Path) -> None:
        super().__init__(text)
        self._file_path = file_path
        self._walked: set[yaml.Node] = set()
        self.keys_written_twice: list[ConfigProblem] = []

    def construct_document(self, node: yaml.Node) -> Any:
        self._record_keys_written_twice(node, key_path="")
        return super().construct_document(node)

    def _record_keys_written_twice(self, node: yaml.Node, *, key_path: str) -> None:
        # An alias is walked once, at its anchor, where its keys are written.
        if node in self._walked:
            return
        self._walked.add(node)
        match node:
            case yaml.MappingNode():
                self._record_in_mapping(node, key_path=key_path)
            case yaml.SequenceNode():
                for index, child in enumerate(node.value):
                    self._record_keys_written_twice(child, key_path=f"{key_path}[{index}]")

    def _record_in_mapping(self, node: yaml.MappingNode, *, key_path: str) -> None:
        first_lines: dict[object, int] = {}
        for key_node, value_node in node.value:
            # The keys a merge key brings may be overridden, so they are not compared.
            if key_node.tag == _MERGE_TAG:
                self._record_keys_written_twice(value_node, key_path=key_path)
                continue
            # A key that is no scalar is unhashable: PyYAML refuses it.
            if not isinstance(key_node, yaml.ScalarNode):
                continue
            key = self.construct_object(key_node)
            key_text = _printable_key(key)
            child_path = f"{key_path}.{key_text}" if key_path else key_text
            line = key_node.start_mark.line + 1
            if key in first_lines:
                self.keys_written_twice.append(
                    ConfigProblem(
                        file_path=self._file_path,
                        key=child_path,
                        message=_written_twice(first_lines[key], line=line),
                    )
                )
            else:
                first_lines[key] = line
            self._record_keys_written_twice(value_node, key_path=child_path)


def _written_twice(first_line: int, *, line: int) -> str:
    if first_line == line:
        return f"written twice on line {line}"
    return f"written twice, at lines {first_line} and {line}"


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
