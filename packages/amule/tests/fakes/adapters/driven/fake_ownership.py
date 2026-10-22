from pathlib import Path


class FakeOwnership:
    """Records each chown it is asked for, or raises ``error``: the gate cannot chown to another
    uid."""

    def __init__(self) -> None:
        self.chowns: list[tuple[Path, int, int]] = []
        self.error: OSError | None = None

    def change_owner(self, path: Path, uid: int, gid: int) -> None:
        if self.error is not None:
            raise self.error
        self.chowns.append((path, uid, gid))
