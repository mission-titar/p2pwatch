from p2pwatch.application.ports.driving.crawl_resumer import CrawlResumer


class FakeCrawlResumer(CrawlResumer):
    """Keeps each call by its operation's name."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def resume_crawl(self) -> None:
        self.calls.append("resume_crawl")
