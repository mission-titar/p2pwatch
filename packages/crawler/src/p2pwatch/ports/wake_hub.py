"""``WakeHub`` port: wakes the in-process loops waiting on a subject (spec orchestration §3).

Coupling by data + wake (spec §3): the loop persists the decision (append-only = free
reliability, a missing consumer replays from the table) THEN ``wake``s the subject, resuming an
in-process consumer immediately. Fallback polling stays the net; a lost wake is harmless.
The "subject" names what a consumer ``await wait(subject)``s on: today only the download loop.

ASYNC Protocol. ``wake`` is synchronous (called from the sync post-commit pipeline, must
never block); ``wait`` is async (the consumer sleeps on it). Implemented on the adapter side
by one ``asyncio.Event`` per subject (``adapters/wake_hub_asyncio.py``).
"""

from typing import Protocol


class WakeHub(Protocol):
    """In-process wake-up hub (spec §3). ``wake`` wakes every ``wait`` on the same subject."""

    def wake(self, subject: str) -> None: ...

    async def wait(self, subject: str) -> None: ...
