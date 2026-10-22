from p2pwatch.application.ports.driving.crawl_pauser import CrawlPauser


class FakeCrawlPauser(CrawlPauser):
    """Keeps each call by its operation's name."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def pause_crawl(self) -> None:
        self.calls.append("pause_crawl")
