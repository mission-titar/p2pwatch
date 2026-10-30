import dataclasses
from typing import Any

import pytest

from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from tests.support.domain.value_bounds import NOT_QUANTITIES, QUANTITIES

_QUANTITY_FIELDS = ("bytes_done", "size_bytes")


def _status() -> DownloadStatus:
    return DownloadStatus(
        file=FileKey(network=Network.ED2K, native_id="31d6cfe0d16ae931b73c59d7e0c089c0"),
        bytes_done=500,
        size_bytes=1000,
        completed=False,
        waiting_reason=None,
        failure_reason=None,
    )


@pytest.mark.parametrize("quantity", NOT_QUANTITIES)
@pytest.mark.parametrize("field", _QUANTITY_FIELDS)
def test_a_download_status_refuses_an_integer_that_is_not_a_quantity(
    *, field: str, quantity: int
) -> None:
    fields: dict[str, Any] = {field: quantity}
    with pytest.raises(ValueError, match=f"^a download status's {field} is not a quantity"):
        dataclasses.replace(_status(), **fields)


@pytest.mark.parametrize("quantity", QUANTITIES)
@pytest.mark.parametrize("field", _QUANTITY_FIELDS)
def test_a_download_status_holds_the_limits_of_a_quantity(*, field: str, quantity: int) -> None:
    fields: dict[str, Any] = {field: quantity}
    status = dataclasses.replace(_status(), **fields)
    assert dataclasses.asdict(status)[field] == quantity
