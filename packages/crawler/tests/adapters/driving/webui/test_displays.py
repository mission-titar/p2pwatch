from p2pwatch.adapters.driving.webui.displays import (
    DbOptionDisplay,
    QueryAnswerDisplay,
    QueryRowDisplay,
)


def test_query_row_holds_cells() -> None:
    assert QueryRowDisplay(cells=("a", "b")).cells == ("a", "b")


def test_query_answer_display_holds_fields() -> None:
    query_answer_display = QueryAnswerDisplay(
        columns=("x",),
        rows=(QueryRowDisplay(cells=("1",)),),
        row_count=1,
        elapsed_ms=3,
        truncated=(),
    )
    assert query_answer_display.columns == ("x",)
    assert query_answer_display.row_count == 1
    assert query_answer_display.truncated == ()


def test_db_option_precomputes_selected_attr() -> None:
    assert DbOptionDisplay(
        value="catalog", label="catalog.db", selected_attr="selected"
    ).selected_attr == ("selected")
