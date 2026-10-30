from pathlib import Path

from p2pwatch_amule.domain.identifiers import Gid, Uid


class FakeOwnership:
    """Records each chown it is asked for, or raises ``error``: the gate cannot chown to another
    uid."""

    def __init__(self) -> None:
        self.chowns: list[tuple[Path, Uid, Gid]] = []
        self.error: OSError | None = None

    def change_owner(self, path: Path, *, uid: Uid, gid: Gid) -> None:
        if self.error is not None:
            raise self.error
        self.chowns.append((path, uid, gid))
