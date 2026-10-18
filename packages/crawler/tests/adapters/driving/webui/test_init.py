import pytest

import p2pwatch.adapters.driving.webui

pytestmark = pytest.mark.usefixtures("close_test_connections")


def test_package_is_importable() -> None:
    assert p2pwatch.adapters.driving.webui.__name__ == "p2pwatch.adapters.driving.webui"
