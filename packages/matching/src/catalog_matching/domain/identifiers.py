"""The identifier this package produces, a type of its own so that mypy refuses a bare str."""

from typing import NewType

TargetId = NewType("TargetId", str)
