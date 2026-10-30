"""Values each side of ``value_bounds``' two bounds, for the tests of the types it guards."""

# What bytes that are not UTF-8 decode to: a lone surrogate, and U+1F600 left as its two halves.
MALFORMED_TEXTS = ("\ud800", "\ud83d\ude00")
# The mapper's replacement character, and a code point beyond U+FFFF.
WELL_FORMED_TEXTS = ("\N{REPLACEMENT CHARACTER}", "\N{GRINNING FACE}")
NOT_QUANTITIES = (-1, 2**63)
# The two limits of a quantity.
QUANTITIES = (0, 2**63 - 1)
