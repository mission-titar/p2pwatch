"""``AmuleBumper``: bumps aMule's pin to upstream's latest release, or says why not."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath

from amule_bump.domain.dockerfile import Pin


@dataclass(frozen=True)
class AmuleBump:
    """The new pin and the pull request body, written unless the bump was a dry run."""

    new_pin: Pin
    body: str


@dataclass(frozen=True)
class PinIsLatest:
    """The pin is upstream's latest release: nothing to do."""

    version: str


@dataclass(frozen=True)
class PinAheadOfLatest:
    """Upstream's latest release is older than the pin: nothing to do."""

    pinned_version: str
    latest_version: str


class AmuleBumper(ABC):
    """Rewrites the Dockerfile's pin and writes the pull request body, if upstream released."""

    @abstractmethod
    def bump_amule(
        self, dockerfile_path: PurePath, body_path: PurePath, *, dry_run: bool
    ) -> AmuleBump | PinIsLatest | PinAheadOfLatest:
        """Writes nothing on a dry run; raises ``BumpError``, or ``OSError`` when I/O fails."""
