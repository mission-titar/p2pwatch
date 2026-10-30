"""Recompute a file's match explanation with the engine the crawl judges with (spec W-D7).

``size_bytes is None`` builds the ``FileCandidate`` directly: the canonical converter
``candidate_from_fields`` requires the size a persisted observation always has.
"""

from collections.abc import Iterable
from dataclasses import replace

from catalog_matching.domain.engine import Explanation, MatchingEngine
from catalog_matching.domain.identifiers import TargetId
from catalog_matching.domain.models import FileCandidate
from p2pwatch.domain.observation import candidate_from_fields


class MatchingExplainer:
    """Explains a file's match with the engine it is given, shared since it keeps no state."""

    def __init__(self, *, engine: MatchingEngine) -> None:
        self._engine = engine

    def explain(
        self,
        filenames: Iterable[str],
        size_bytes: int | None,
        duration_seconds: int | None,
        bitrate_kbps: int | None,
        target_id: TargetId,
    ) -> Explanation | None:
        """Recompute the explanation of target ``target_id`` over every filename of one file.

        Each filename carries the same fields, as ``FileJudge`` judges a file.
        Return ``None`` if ``target_id`` is unknown to the current config.
        """
        if size_bytes is None:
            base_candidate = FileCandidate(
                filename="",
                size_mib=None,
                duration_seconds=float(duration_seconds) if duration_seconds is not None else None,
                bitrate_kbps=float(bitrate_kbps) if bitrate_kbps is not None else None,
            )
        else:
            base_candidate = candidate_from_fields("", size_bytes, duration_seconds, bitrate_kbps)
        candidates = [replace(base_candidate, filename=filename) for filename in filenames]
        return self._engine.explain(candidates, target_id=target_id)
