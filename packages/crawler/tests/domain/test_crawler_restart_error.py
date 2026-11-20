from p2pwatch.domain.crawler_restart_error import CrawlerRestartError


def test_it_reads_as_the_object_rebuilt_in_vain_and_how_many_times() -> None:
    error = CrawlerRestartError("client amuled", rebuilds=3)

    assert (str(error), error.restartable, error.rebuilds) == (
        "client amuled rebuilt 3 times in vain",
        "client amuled",
        3,
    )
