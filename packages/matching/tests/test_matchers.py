import pytest

from catalog_matching.matchers import (
    READERS_BY_ATTR,
    AttrBetweenMatcher,
    CoverageMatcher,
    KeywordMatcher,
    RegexMatcher,
)
from catalog_matching.models import FileCandidate


def test_keyword_single_word_present() -> None:
    matcher = KeywordMatcher("keroro")
    assert matcher.matches(FileCandidate(filename="Keroro 062A.avi")) is True


def test_keyword_single_word_absent() -> None:
    matcher = KeywordMatcher("titar")
    assert matcher.matches(FileCandidate(filename="Keroro 062A.avi")) is False


def test_keyword_multiword_contiguous_present() -> None:
    matcher = KeywordMatcher("mission titar")
    candidate = FileCandidate(filename="Keroro Mission Titar 062A.avi")
    assert matcher.matches(candidate) is True


def test_keyword_multiword_non_contiguous_absent() -> None:
    matcher = KeywordMatcher("mission titar")
    candidate = FileCandidate(filename="mission keroro titar.avi")
    assert matcher.matches(candidate) is False


def test_keyword_accent_and_case_insensitive_via_tokenize() -> None:
    matcher = KeywordMatcher("teletoon")
    assert matcher.matches(FileCandidate(filename="Keroro TÉLÉTOON.avi")) is True


def test_keyword_empty_phrase_matches_anything() -> None:
    matcher = KeywordMatcher("")
    assert matcher.matches(FileCandidate(filename="whatever.avi")) is True


def test_keyword_phrase_longer_than_filename_is_absent() -> None:
    matcher = KeywordMatcher("keroro mission titar special")
    assert matcher.matches(FileCandidate(filename="keroro mission titar.avi")) is False


def test_regex_literal_matches_case_and_accent_insensitive() -> None:
    # The literal pattern "teletoon" matches "Télétoon" thanks to fold(raw).
    matcher = RegexMatcher("teletoon")
    assert matcher.matches(FileCandidate(filename="Keroro Télétoon.avi")) is True


def test_regex_segment_id_style_pattern() -> None:
    matcher = RegexMatcher(r"n[°o]?\s*0*62\s*a")
    assert matcher.matches(FileCandidate(filename="Keroro N°062A.avi")) is True


def test_regex_no_match_returns_false() -> None:
    matcher = RegexMatcher("teletoon")
    assert matcher.matches(FileCandidate(filename="other file.mkv")) is False


def test_regex_uppercase_pattern_without_i_flag_does_not_match_folded_input() -> None:
    # fold() already lowercases; an UPPERCASE pattern without (?i) does not match.
    matcher = RegexMatcher("TELETOON", flags="")
    assert matcher.matches(FileCandidate(filename="Keroro Télétoon.avi")) is False


def test_coverage_exact_title_is_one_and_matches() -> None:
    matcher = CoverageMatcher("Les demoiselles cambrioleuses", min_coverage=0.6)
    candidate = FileCandidate(filename="Keroro 062A Les demoiselles cambrioleuses.avi")
    assert matcher.coverage(candidate) == 1.0
    assert matcher.matches(candidate) is True


def test_coverage_one_typo_within_fuzz_still_matches() -> None:
    matcher = CoverageMatcher("Les demoiselles cambrioleuses", min_coverage=0.6)
    # "demoiseles" (one missing 'l') stays >= min_similarity 0.85 vs "demoiselles".
    candidate = FileCandidate(filename="demoiseles cambrioleuses.avi")
    assert matcher.coverage(candidate) == 1.0
    assert matcher.matches(candidate) is True


def test_coverage_unrelated_is_zero_and_no_match() -> None:
    matcher = CoverageMatcher("Les demoiselles cambrioleuses", min_coverage=0.6)
    candidate = FileCandidate(filename="totalement autre chose.mkv")
    assert matcher.coverage(candidate) == 0.0
    assert matcher.matches(candidate) is False


def test_coverage_empty_reference_is_zero() -> None:
    # Reference made only of stopwords -> no significant token -> 0.0.
    matcher = CoverageMatcher("les des un une", min_coverage=0.6)
    candidate = FileCandidate(filename="les demoiselles.avi")
    assert matcher.coverage(candidate) == 0.0
    assert matcher.matches(candidate) is False


def test_coverage_partial_fraction_at_min_boundary_matches() -> None:
    # 1 significant word covered out of 2 -> coverage 0.5 >= min_coverage 0.5 -> match.
    matcher = CoverageMatcher("demoiselles cambrioleuses", min_coverage=0.5)
    candidate = FileCandidate(filename="demoiselles autre.avi")
    assert matcher.coverage(candidate) == 0.5
    assert matcher.matches(candidate) is True


def test_coverage_partial_fraction_below_min_does_not_match() -> None:
    # Same coverage 0.5 but min_coverage 0.6 -> below the threshold -> no match.
    matcher = CoverageMatcher("demoiselles cambrioleuses", min_coverage=0.6)
    candidate = FileCandidate(filename="demoiselles autre.avi")
    assert matcher.coverage(candidate) == 0.5
    assert matcher.matches(candidate) is False


def test_each_attr_reads_its_candidate_field() -> None:
    candidate = FileCandidate(
        filename="x.avi", size_mib=1.0, duration_seconds=2.0, bitrate_kbps=3.0
    )
    assert {attr: read(candidate) for attr, read in READERS_BY_ATTR.items()} == {
        "size_mib": 1.0,
        "duration_seconds": 2.0,
        "bitrate_kbps": 3.0,
    }


def test_attr_between_unknown_attr_raises() -> None:
    with pytest.raises(ValueError) as excinfo:
        AttrBetweenMatcher("codec", min_bound=1.0)
    message = str(excinfo.value)
    assert "codec" in message
    # the message lists the valid attributes to guide the config author
    assert "size_mib" in message
    assert "duration_seconds" in message
    assert "bitrate_kbps" in message


def test_attr_between_absent_value_is_false() -> None:
    matcher = AttrBetweenMatcher("size_mib", min_bound=30.0, max_bound=600.0)
    assert matcher.matches(FileCandidate(filename="x.avi")) is False


def test_attr_between_in_range_is_true() -> None:
    matcher = AttrBetweenMatcher("size_mib", min_bound=30.0, max_bound=600.0)
    assert matcher.matches(FileCandidate(filename="x.avi", size_mib=120.0)) is True


def test_attr_between_below_min_is_false() -> None:
    matcher = AttrBetweenMatcher("size_mib", min_bound=30.0, max_bound=600.0)
    assert matcher.matches(FileCandidate(filename="x.avi", size_mib=10.0)) is False


def test_attr_between_above_max_is_false() -> None:
    matcher = AttrBetweenMatcher("size_mib", min_bound=30.0, max_bound=600.0)
    assert matcher.matches(FileCandidate(filename="x.avi", size_mib=900.0)) is False


def test_attr_between_open_lower_bound() -> None:
    matcher = AttrBetweenMatcher("duration_seconds", max_bound=1800.0)
    assert matcher.matches(FileCandidate(filename="x.avi", duration_seconds=10.0)) is True
    assert matcher.matches(FileCandidate(filename="x.avi", duration_seconds=2000.0)) is False


def test_attr_between_open_upper_bound() -> None:
    matcher = AttrBetweenMatcher("bitrate_kbps", min_bound=500.0)
    assert matcher.matches(FileCandidate(filename="x.avi", bitrate_kbps=900.0)) is True
    assert matcher.matches(FileCandidate(filename="x.avi", bitrate_kbps=100.0)) is False


def test_attr_between_no_bounds_accepts_any_present_value() -> None:
    matcher = AttrBetweenMatcher("size_mib")
    assert matcher.matches(FileCandidate(filename="x.avi", size_mib=1.0)) is True
