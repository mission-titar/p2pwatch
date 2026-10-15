"""The record a check emits when a premise is falsified."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    advisory_id: str
    message: str
    location: str  # repo-relative path pointing at the offending file
