"""A JSON object as its canonical text: what a network sent that no field consumes."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from p2pwatch.domain.value_bounds import require_well_formed_text


@dataclass(kw_only=True, frozen=True)
class JsonText:
    """The canonical text of a JSON object: as ``json.dumps`` writes it, keys sorted, non-ASCII
    unescaped; valid UTF-8, no ``NaN`` nor infinity. Equal content, equal text."""

    text: str

    def __post_init__(self) -> None:
        try:
            json_object = json.loads(self.text)
        except (ValueError, RecursionError) as error:
            raise ValueError("a JSON text does not parse") from error
        if not isinstance(json_object, dict):
            raise ValueError("a JSON text is not an object")
        try:
            canonical_text = _canonical_text(json_object, allow_nan=False)
        except ValueError as error:
            raise ValueError("a JSON text holds a number that is not finite") from error
        if canonical_text != self.text:
            raise ValueError("a JSON text is not in its canonical form")
        require_well_formed_text(self.text, error_label="a JSON text")

    @classmethod
    def from_object(cls, json_object: Mapping[str, object]) -> Self:
        """``json_object`` written as its canonical text, which the guard then checks."""
        return cls(text=_canonical_text(dict(json_object), allow_nan=True))


def _canonical_text(json_object: dict[str, object], *, allow_nan: bool) -> str:
    return json.dumps(json_object, ensure_ascii=False, sort_keys=True, allow_nan=allow_nan)
