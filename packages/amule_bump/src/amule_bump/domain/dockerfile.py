import re
from dataclasses import dataclass
from pathlib import PurePath

from amule_bump.domain.bump_error import BumpError

DOCKERFILE_PATH = PurePath("packages/amule/Dockerfile")  # under the repository's root


@dataclass(frozen=True)
class Pin:
    version: str
    commit: str

    def arg_lines(self) -> str:
        return "\n".join(
            (_arg_line("AMULE_VERSION", self.version), _arg_line("AMULE_COMMIT", self.commit))
        )


def read_pin(dockerfile_text: str) -> Pin:
    return Pin(
        _arg_value(dockerfile_text, "AMULE_VERSION"), _arg_value(dockerfile_text, "AMULE_COMMIT")
    )


def rewrite_pin(dockerfile_text: str, pin: Pin) -> str:
    dockerfile_text = _arg_line_pattern("AMULE_VERSION").sub(
        _arg_line("AMULE_VERSION", pin.version), dockerfile_text
    )
    return _arg_line_pattern("AMULE_COMMIT").sub(
        _arg_line("AMULE_COMMIT", pin.commit), dockerfile_text
    )


def _arg_line(name: str, value: str) -> str:
    return f"ARG {name}={value}"


def _arg_value(dockerfile_text: str, name: str) -> str:
    # Exactly one line, or the rewrite would be ambiguous.
    values = _arg_line_pattern(name).findall(dockerfile_text)
    if len(values) != 1:
        raise BumpError(f"expected one 'ARG {name}=' line, found {len(values)}")
    return str(values[0])


def _arg_line_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"^ARG {name}=(.*)$", re.MULTILINE)
