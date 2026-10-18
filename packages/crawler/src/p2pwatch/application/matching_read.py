"""Recompute a match explanation from an already-parsed config (spec W-D7 / Task 9).

Since P4a ``MatchingExplainer`` takes the crawler's ALREADY-PARSED ``MatcherConfig`` +
``targets`` tuple at construction time (the YAML → config parsing moved UP into the caller:
``__main__`` for the standalone entrypoint, ``CrawlerApp`` in-process later). It builds the
:class:`MatchingEngine` ONCE and exposes ``explain()`` to recompute a file's explanation over
all its filenames against that config. Sharing the crawler's own parsed matcher is what kills the
matcher-drift bug structurally (spec §8).

``size_bytes → size_mib`` (and the trivial ``int → float`` casts) reuse the crawler's ONE
canonical converter, ``p2pwatch.domain.observation.candidate_from_fields`` (which encodes
DECISION 8: eMule "MB" are binary Mio); the monolith consolidation removed the old boundary
that forced this module to reimplement it. The ONLY case that cannot go through the canonical
converter is ``size_bytes is None``: the converter requires an ``int`` (a persisted
observation always has a size), while ``explain()``'s contract still permits ``None``, so that
path builds the ``FileCandidate`` directly.
"""

from collections.abc import Iterable
from dataclasses import replace

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.engine import Explanation, MatchingEngine
from catalog_matching.domain.models import FileCandidate, TargetSegment
from p2pwatch.domain.observation import candidate_from_fields


class MatchingExplainer:
    """Build and cache a :class:`MatchingEngine` from a parsed config.

    The engine is resolved ONCE (matcher trees pre-compiled per target) at
    construction. Successive calls to ``explain()`` reuse the same engine.
    """

    def __init__(
        self, *, matcher_config: MatcherConfig, targets: tuple[TargetSegment, ...]
    ) -> None:
        self._engine = MatchingEngine(matcher_config, targets)

    def explain(
        self,
        filenames: Iterable[str],
        size_bytes: int | None,
        duration_seconds: int | None,
        bitrate_kbps: int | None,
        target_id: str,
    ) -> Explanation | None:
        """Recompute the explanation of target ``target_id`` over every filename of one file.

        Each filename carries the same fields, as ``rejudge_file`` judges a file.
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
        return self._engine.explain(candidates, target_id)
