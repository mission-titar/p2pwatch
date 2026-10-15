from p2pwatch.ports.client_errors import (
    ClientError,
    ClientUnreachableError,
    DownloadRejectedError,
    SearchFailedError,
)


def test_unreachable_search_failed_and_download_rejected_are_client_errors() -> None:
    assert issubclass(ClientUnreachableError, ClientError)
    assert issubclass(SearchFailedError, ClientError)
    assert issubclass(DownloadRejectedError, ClientError)


def test_search_failed_and_download_rejected_are_distinct() -> None:
    assert not issubclass(SearchFailedError, DownloadRejectedError)
    assert not issubclass(DownloadRejectedError, SearchFailedError)
