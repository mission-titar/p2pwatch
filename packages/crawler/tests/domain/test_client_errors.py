from p2pwatch.domain.client_errors import (
    ClientError,
    ClientUnreachableError,
    DownloadRejectedError,
    ReadRejectedError,
    SearchFailedError,
)


def test_unreachable_and_each_refusal_are_client_errors() -> None:
    assert issubclass(ClientUnreachableError, ClientError)
    assert issubclass(SearchFailedError, ClientError)
    assert issubclass(DownloadRejectedError, ClientError)
    assert issubclass(ReadRejectedError, ClientError)


def test_each_operation_refusal_is_distinct() -> None:
    refusals = (SearchFailedError, DownloadRejectedError, ReadRejectedError)
    for refusal in refusals:
        assert [other for other in refusals if issubclass(refusal, other)] == [refusal]
