"""The first requests to aMule: the status reading's and download tracking's before the
searches'."""

from p2pwatch.application.steps.work import Work
from p2pwatch.composition.crawler_composition import works_in_start_order


class _NamedWork(Work):
    """A work known by its name alone: these tests never take its turns."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def wait_for_next_turn(self) -> None:
        """Never called."""

    async def run_once(self) -> None:
        """Never called."""


def test_the_status_reading_starts_first_then_download_and_source_tracking_then_the_searches() -> (
    None
):
    works = works_in_start_order(
        status_watcher=_NamedWork("status"),
        tracking=(_NamedWork("downloads"), _NamedWork("sources")),
        searches=(_NamedWork("ed2k keroro"), _NamedWork("kad keroro")),
    )
    assert [work.name for work in works if isinstance(work, _NamedWork)] == [
        "status",
        "downloads",
        "sources",
        "ed2k keroro",
        "kad keroro",
    ]


def test_without_download_the_status_reading_starts_before_the_searches() -> None:
    works = works_in_start_order(
        status_watcher=_NamedWork("status"), tracking=(), searches=(_NamedWork("kad keroro"),)
    )
    assert [work.name for work in works if isinstance(work, _NamedWork)] == ["status", "kad keroro"]
