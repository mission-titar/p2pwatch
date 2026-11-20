"""The error the crawler stops with so that Docker starts it again whole, which the command line
reports before exiting non-zero."""


class CrawlerRestartError(Exception):
    """An object, such as ``client amuled``, rebuilt ``rebuilds`` times in vain: the cause lies
    in something shared, which only a new process renews."""

    def __init__(self, restartable: str, *, rebuilds: int) -> None:
        super().__init__(f"{restartable} rebuilt {rebuilds} times in vain")
        self.restartable = restartable
        self.rebuilds = rebuilds
