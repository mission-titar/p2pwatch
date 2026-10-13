"""Startup gate for the catalogue re-evaluation: skip when the policy is unchanged (spec §7.1).

APPLICATION layer, pure orchestration (no I/O of its own: delegates to the injected
``local_repo`` port and the ``reevaluate`` callable, so the composition root decides what
re-evaluating concretely means, e.g. ``reevaluate_catalog``).

Crash safety (spec §7.1): the marker is stored ONLY after ``reevaluate`` returns
successfully. If it raises, the exception propagates here UNCHANGED and the marker is left
untouched: the next start sees the same (or no) fingerprint and retries the full pass.
"""

from collections.abc import Awaitable, Callable

from p2pwatch.application.reevaluate_catalog import ReevaluationSummary
from p2pwatch.ports.local_state_repository import LocalStateRepository


async def reevaluate_if_policy_changed(
    *,
    fingerprint: str,
    local_repo: LocalStateRepository,
    reevaluate: Callable[[], Awaitable[ReevaluationSummary]],
) -> ReevaluationSummary | None:
    """Re-evaluates iff the stored policy fingerprint differs from ``fingerprint``.

    ``None`` when skipped (the marker already equals ``fingerprint``); the re-evaluation's
    ``ReevaluationSummary`` otherwise, once the marker has been updated to ``fingerprint``.
    """
    if local_repo.reevaluated_policy_fingerprint() == fingerprint:
        return None
    summary = await reevaluate()
    local_repo.set_reevaluated_policy_fingerprint(fingerprint)
    return summary
