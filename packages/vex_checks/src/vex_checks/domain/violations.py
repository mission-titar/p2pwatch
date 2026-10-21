"""The record a check emits when a premise is falsified."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    advisory_id: str
    message: str
    location: str  # the offending file, relative to the repository's root or as given outside it
