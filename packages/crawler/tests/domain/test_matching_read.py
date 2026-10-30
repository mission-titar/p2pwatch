"""``MatchingExplainer``: a file's explanation over every filename, from the engine it is given."""

import yaml

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.engine import Explanation, MatchingEngine
from catalog_matching.domain.identifiers import TargetId
from catalog_matching.domain.models import TargetSegment
from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.domain.matching_read import MatchingExplainer

_MAX_FILENAME_LENGTH = 4096

# ---------------------------------------------------------------------------
# Parsed-config minimal helpers
# ---------------------------------------------------------------------------


def _minimal_targets() -> tuple[TargetSegment, ...]:
    return parse_targets(
        yaml.safe_load(
            """\
episodes:
  - season: 2
    seasonal_number: 11
    absolute_number: 62
    segments:
      - letter: a
        title: "La Grenouille Cosmique"
"""
        )
    )


def _minimal_matcher() -> MatcherConfig:
    """Minimal matcher: keyword token 'keroro' + catalog rule."""
    return parse_matcher_config(
        yaml.safe_load(
            """\
tokens:
  keroro:
    keyword: keroro
rules:
  - name: catalog
    tier: catalog
    scope: unattributed
    any:
      - keroro
"""
        )
    )


# ---------------------------------------------------------------------------
# Tests: explain()
# ---------------------------------------------------------------------------


def test_explainer_returns_explanation_on_matching_filename() -> None:
    """Filename containing 'keroro' → Explanation with non-empty rules_fired."""
    explainer = MatchingExplainer(
        engine=MatchingEngine(
            _minimal_matcher(), targets=_minimal_targets(), max_filename_length=_MAX_FILENAME_LENGTH
        )
    )
    explanation = explainer.explain(
        filenames=["Keroro_062A_VF.avi"],
        size_bytes=None,
        duration_seconds=None,
        bitrate_kbps=None,
        target_id=TargetId("062A"),
    )
    assert isinstance(explanation, Explanation)
    assert len(explanation.rules_fired) > 0
    assert explanation.target_id == "062A"


def test_explainer_returns_none_for_unknown_target() -> None:
    """target_id unknown to the config → None."""
    explainer = MatchingExplainer(
        engine=MatchingEngine(
            _minimal_matcher(), targets=_minimal_targets(), max_filename_length=_MAX_FILENAME_LENGTH
        )
    )
    explanation = explainer.explain(
        filenames=["Keroro_062A_VF.avi"],
        size_bytes=None,
        duration_seconds=None,
        bitrate_kbps=None,
        target_id=TargetId("S9E999Z"),
    )
    assert explanation is None


def test_explainer_size_bytes_converted_to_mb() -> None:
    """size_bytes → size_mib via MiB conversion (1024*1024).

    We verify the FileCandidate is built without error with size_bytes provided.
    An attr_between matcher on size_mib lets us verify the passed value.
    """
    # Matcher with an attr_between token on size_mib: exactly 100 MiB
    matcher_config = parse_matcher_config(
        yaml.safe_load(
            """\
tokens:
  keroro:
    keyword: keroro
  size_ok:
    attr_between: size_mib
    min: 99.9
    max: 100.1
rules:
  - name: catalog
    tier: catalog
    scope: unattributed
    all:
      - keroro
      - size_ok
"""
        )
    )

    explainer = MatchingExplainer(
        engine=MatchingEngine(
            matcher_config, targets=_minimal_targets(), max_filename_length=_MAX_FILENAME_LENGTH
        )
    )
    # 100 * 1024 * 1024 = 104857600 bytes = exactly 100.0 MiB
    explanation = explainer.explain(
        filenames=["keroro_062a.avi"],
        size_bytes=104857600,
        duration_seconds=None,
        bitrate_kbps=None,
        target_id=TargetId("062A"),
    )
    assert isinstance(explanation, Explanation)
    assert "catalog" in explanation.rules_fired


def test_explainer_media_length_and_bitrate_forwarded() -> None:
    """duration_seconds and bitrate_kbps are forwarded as-is to the FileCandidate."""
    # Matcher with attr_between on duration_seconds and bitrate_kbps
    matcher_config = parse_matcher_config(
        yaml.safe_load(
            """\
tokens:
  keroro:
    keyword: keroro
  dur_ok:
    attr_between: duration_seconds
    min: 1300.0
    max: 1400.0
  bit_ok:
    attr_between: bitrate_kbps
    min: 1000.0
    max: 2000.0
rules:
  - name: catalog
    tier: catalog
    scope: unattributed
    all:
      - keroro
      - dur_ok
      - bit_ok
"""
        )
    )

    explainer = MatchingExplainer(
        engine=MatchingEngine(
            matcher_config, targets=_minimal_targets(), max_filename_length=_MAX_FILENAME_LENGTH
        )
    )
    explanation = explainer.explain(
        filenames=["keroro_062a.avi"],
        size_bytes=None,
        duration_seconds=1350,
        bitrate_kbps=1500,
        target_id=TargetId("062A"),
    )
    assert isinstance(explanation, Explanation)
    assert "catalog" in explanation.rules_fired


def test_explainer_judges_every_name_and_lists_the_vetoes_fired() -> None:
    """A veto fired by one name of the file shows up, with the rules fired by another name."""
    matcher_config = parse_matcher_config(
        yaml.safe_load(
            """\
tokens:
  keroro:
    keyword: keroro
  ita:
    regex: "\\\\bITA\\\\b"
  big:
    attr_between: size_mib
    min: 99.9
vetoes: [ita]
rules:
  - name: catalog
    tier: catalog
    scope: unattributed
    all: [keroro, big]
"""
        )
    )
    explainer = MatchingExplainer(
        engine=MatchingEngine(
            matcher_config, targets=_minimal_targets(), max_filename_length=_MAX_FILENAME_LENGTH
        )
    )
    explanation = explainer.explain(
        filenames=["ita.avi", "keroro.avi"],
        size_bytes=100 * 1024 * 1024,
        duration_seconds=None,
        bitrate_kbps=None,
        target_id=TargetId("062A"),
    )
    assert isinstance(explanation, Explanation)
    assert explanation.vetoes_fired == ("ita",)
    assert explanation.rules_fired == ("catalog",)  # the size applies to every name
