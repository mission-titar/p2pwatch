from catalog_matching.domain.ed2k_link import build_ed2k_link

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"


def test_simple_name_builds_canonical_link() -> None:
    link = build_ed2k_link("Keroro 062A.avi", size_bytes=12345, native_id=_HASH)
    assert link == f"ed2k://|file|Keroro%20062A.avi|12345|{_HASH}|/"


def test_pipe_in_name_is_escaped() -> None:
    # the '|' is the link's field separator: it MUST be escaped (%7C) otherwise the
    # framing breaks (a hostile name must never inject a field).
    link = build_ed2k_link("weird|name.avi", size_bytes=99, native_id=_HASH)
    assert "%7C" in link
    assert link.count("|") == 5  # only the 5 structural separators of the link


def test_non_ascii_name_is_utf8_percent_encoded() -> None:
    link = build_ed2k_link("accentué.mkv", size_bytes=1, native_id=_HASH)
    assert "accentu%C3%A9.mkv" in link


def test_zero_size_is_serialized() -> None:
    link = build_ed2k_link("x.avi", size_bytes=0, native_id=_HASH)
    assert link == f"ed2k://|file|x.avi|0|{_HASH}|/"


def test_hash_is_placed_verbatim() -> None:
    link = build_ed2k_link("a.bin", size_bytes=5, native_id=_HASH)
    assert link.endswith(f"|{_HASH}|/")
