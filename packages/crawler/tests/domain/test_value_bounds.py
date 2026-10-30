import re

import pytest

from p2pwatch.domain.value_bounds import require_quantity, require_well_formed_text
from tests.support.domain.value_bounds import (
    MALFORMED_TEXTS,
    NOT_QUANTITIES,
    QUANTITIES,
    WELL_FORMED_TEXTS,
)


@pytest.mark.parametrize("surrogates", [*MALFORMED_TEXTS, "\udfff"])
def test_a_text_holding_a_surrogate_is_not_well_formed(surrogates: str) -> None:
    with pytest.raises(ValueError, match="^a filename is not valid UTF-8$"):
        require_well_formed_text(f"Keroro {surrogates}.avi", error_label="a filename")


@pytest.mark.parametrize("text", [*WELL_FORMED_TEXTS, chr(0xD7FF), chr(0xE000), "", None])
def test_a_text_beside_the_surrogates_or_none_passes(text: str | None) -> None:
    require_well_formed_text(text, error_label="a filename")


@pytest.mark.parametrize("quantity", NOT_QUANTITIES)
def test_an_integer_below_0_or_past_the_catalogs_integer_is_not_a_quantity(quantity: int) -> None:
    message = f"a size is not a quantity in [0, 2**63): {quantity}"
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        require_quantity(quantity, error_label="a size")


@pytest.mark.parametrize("quantity", [*QUANTITIES, None])
def test_the_limits_of_a_quantity_or_none_pass(quantity: int | None) -> None:
    require_quantity(quantity, error_label="a size")
