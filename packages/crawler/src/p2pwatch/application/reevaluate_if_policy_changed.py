"""Startup gate for the catalogue re-evaluation: skip when the policy is unchanged (spec §7.1).

APPLICATION layer, pure orchestration (no I/O of its own: delegates to the injected
``local_repo`` port and the ``reevaluate`` callable, so the composition root decides what
re-evaluating concretely means, e.g. ``reevaluate_catalog``).

Crash safety (spec §7.1): the marker is stored ONLY after ``reevaluate`` returns
successfully. If it raises, the exception propagates here UNCHANGED and the marker is left
untouched: the next start sees the same (or no) fingerprint and retries the full pass.
"""

import logging
from collections.abc import Awaitable, Callable

from p2pwatch.application.reevaluate_catalog import ReevaluationSummary
from p2pwatch.ports.local_state_repository import LocalStateRepository

_logger = logging.getLogger("p2pwatch.application.reevaluate_if_policy_changed")


async def reevaluate_if_policy_changed(
    *,
    fingerprint: str,
    local_repo: LocalStateRepository,
    reevaluate: Callable[[], Awaitable[ReevaluationSummary]],
) -> None:
    """Re-evaluates iff the stored policy fingerprint differs from ``fingerprint``, then stores
    it; logs either outcome."""
    if local_repo.reevaluated_policy_fingerprint() == fingerprint:
        _logger.info("policy unchanged: catalogue re-evaluation skipped")
        return
    summary = await reevaluate()
    local_repo.set_reevaluated_policy_fingerprint(fingerprint)
    _logger.info(
        "catalogue re-evaluated: %d files, %d rows written",
        summary.files_evaluated,
        summary.rows_written,
    )
