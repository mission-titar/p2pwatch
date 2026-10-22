from pathlib import PurePath

from p2pwatch.application.ports.driving.crawler_runner import CrawlerRunner


class FakeCrawlerRunner(CrawlerRunner):
    """Records the paths of each crawl, and raises ``failure`` when given one."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.crawled_paths: list[tuple[PurePath, PurePath, PurePath]] = []
        self._failure = failure

    async def crawl(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        self.crawled_paths.append((config_path, targets_path, matcher_path))
        if self._failure is not None:
            raise self._failure
