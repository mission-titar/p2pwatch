import pytest

from p2pwatch.webui.domain.views import ConsoleResult, ConsoleRow, DbOption

pytestmark = pytest.mark.usefixtures("close_test_connections")


def test_console_row_holds_cells() -> None:
    assert ConsoleRow(cells=("a", "b")).cells == ("a", "b")


def test_console_result_holds_fields() -> None:
    result = ConsoleResult(
        columns=("x",),
        rows=(ConsoleRow(cells=("1",)),),
        row_count=1,
        elapsed_ms=3,
        truncated=(),
    )
    assert result.columns == ("x",)
    assert result.row_count == 1
    assert result.truncated == ()


def test_db_option_precomputes_selected_attr() -> None:
    assert DbOption(
        value="catalog", label="catalog.db", selected_attr="selected"
    ).selected_attr == ("selected")
