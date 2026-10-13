import re
from dataclasses import dataclass

from amule_bump import BumpError


@dataclass(frozen=True)
class Pin:
    version: str
    commit: str

    def arg_lines(self) -> str:
        return f"ARG AMULE_VERSION={self.version}\nARG AMULE_COMMIT={self.commit}"


def read_pin(dockerfile_text: str) -> Pin:
    return Pin(
        _arg_value(dockerfile_text, "AMULE_VERSION"), _arg_value(dockerfile_text, "AMULE_COMMIT")
    )


def rewrite_pin(dockerfile_text: str, pin: Pin) -> str:
    dockerfile_text = _arg_line_pattern("AMULE_VERSION").sub(
        f"ARG AMULE_VERSION={pin.version}", dockerfile_text
    )
    return _arg_line_pattern("AMULE_COMMIT").sub(f"ARG AMULE_COMMIT={pin.commit}", dockerfile_text)


def _arg_value(dockerfile_text: str, name: str) -> str:
    # Exactly one line, or the rewrite would be ambiguous.
    values = _arg_line_pattern(name).findall(dockerfile_text)
    if len(values) != 1:
        raise BumpError(f"expected one 'ARG {name}=' line, found {len(values)}")
    return str(values[0])


def _arg_line_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"^ARG {name}=(.*)$", re.MULTILINE)
