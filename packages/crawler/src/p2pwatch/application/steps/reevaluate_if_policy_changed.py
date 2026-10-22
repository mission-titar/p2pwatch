"""Startup gate for the catalogue re-evaluation: skip when the policy is unchanged (spec §7.1).

APPLICATION ring, pure orchestration (no I/O of its own: delegates to the injected
policy fingerprint ports and the ``reevaluate`` callable, so the composition root decides what
re-evaluating concretely means, e.g. ``reevaluate_catalog``).

Crash safety (spec §7.1): the marker is stored ONLY after ``reevaluate`` returns
successfully. If it raises, the exception propagates here UNCHANGED and the marker is left
untouched: the next start sees the same (or no) fingerprint and retries the full pass.
"""

from collections.abc import Awaitable, Callable

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.policy_fingerprint_reader import PolicyFingerprintReader
from p2pwatch.application.ports.driven.policy_fingerprint_writer import PolicyFingerprintWriter
from p2pwatch.application.steps.reevaluate_catalog import ReevaluationSummary


async def reevaluate_if_policy_changed(
    *,
    fingerprint: str,
    policy_fingerprint_reader: PolicyFingerprintReader,
    policy_fingerprint_writer: PolicyFingerprintWriter,
    reevaluate: Callable[[], Awaitable[ReevaluationSummary]],
    logger: Logger,
) -> None:
    """Re-evaluates iff the stored policy fingerprint differs from ``fingerprint``, then stores
    it; logs either outcome."""
    if policy_fingerprint_reader.read_policy_fingerprint() == fingerprint:
        logger.info("policy unchanged: catalogue re-evaluation skipped")
        return
    summary = await reevaluate()
    policy_fingerprint_writer.set_policy_fingerprint(fingerprint)
    logger.info(
        "catalogue re-evaluated: %d files, %d rows written",
        summary.files_evaluated,
        summary.rows_written,
    )
