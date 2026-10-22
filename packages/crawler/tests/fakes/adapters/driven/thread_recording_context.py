import threading
from contextlib import AbstractContextManager


class FakeServingResource(AbstractContextManager[None]):
    """Records the thread that enters it and the one that leaves it."""

    def __init__(self) -> None:
        self.threads: list[tuple[str, str]] = []

    def __enter__(self) -> None:
        self.threads.append(("enter", threading.current_thread().name))

    def __exit__(self, *exc_info: object) -> None:
        self.threads.append(("exit", threading.current_thread().name))
