"""The download loop: reconcile → completions → new candidates → sources → sleep/wake (spec §5).

One serial task. ``DownloadCycle.run`` runs ONE iteration;
``DownloadLoop`` repeats it until shutdown, waiting ``poll_interval`` or the download wake.
Three things in it are not obvious:

- **A completion is the client's own signal, never the bytes** (2026-09-02: 065B was stamped
  complete at 20.1 %). ``DownloadStatus.completed`` carries it.
- **A download's absence is measured on the monotonic clock** (monotonic clock spec, D7).
  ``latest_seen_at`` only carries it across a restart, clamped by ``remaining_wait``: a wall-clock
  step fails nothing.
- **A download the client does not list is started again**, once per round, until it is listed
  or the TTL fails it: a client may forget its transfers on restart.

Errors: ``ClientUnreachableError``, a refused read and ``OSError`` on the disk measurement skip
the iteration, ``StoreError`` is logged and the cycle continues. A stalled download is never
abandoned.
"""

from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.download_decider import DownloadDecider
from p2pwatch.application.steps.download_starter import DownloadStarter
from p2pwatch.application.steps.download_tracker import DownloadTracker
from p2pwatch.application.steps.source_watcher import SourceWatcher
from p2pwatch.domain.client_errors import ClientUnreachableError, ReadRejectedError
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.store_error import StoreError

# A read the client refuses is the daemon unavailable.
_UNAVAILABLE = (ClientUnreachableError, ReadRejectedError)


class DownloadCycle:
    """One download round over the four stages, under one error doctrine."""

    def __init__(
        self,
        *,
        download_client: DownloadClient,
        download_tracker: DownloadTracker,
        download_decider: DownloadDecider,
        download_starter: DownloadStarter,
        source_watcher: SourceWatcher,
        logger: Logger,
    ) -> None:
        self._download_client = download_client
        self._download_tracker = download_tracker
        self._download_decider = download_decider
        self._download_starter = download_starter
        self._source_watcher = source_watcher
        self._logger = logger

    async def run(self, node_id: NodeId) -> None:
        """ONE iteration of the download loop (spec §5). Never raises: tolerates/absorbs.

        Two distinct error DOCTRINES (item I2 - anti-starvation):

        - An unavailable client (``ClientUnreachableError`` from step 0, ``start_unlisted`` or the
          sources step; on the two reads, also a refused read, ``ReadRejectedError``) = dead
          client → ABORT the iteration ("a dead client makes everything fail"). We skip the
          rest; the next iteration retries.
        - ``StoreError`` (persistence failure, NO client I/O) → ISOLATED PER STEP: a store
          failure in one step must NOT starve the others. Each step that can raise
          ``StoreError`` is wrapped separately (log + ``continue`` to the next step), and the
          sources step per download. ``start_unlisted`` re-reads ``read_tracked_states``
          FRESHLY, so it runs even if an upstream step partially failed. "NEVER abandon a
          stalled download": the 1→2→3→4 order is preserved, each step is best-effort, and
          step 5, the sources, only observes, so it comes last (stage 4, D8).

        The stores are sync → cancellation (shutdown) lands at the network ``await``, never
        mid-write.

        DECISION (audit 2026-06-23 / observability#5): a ``ClientUnreachableError`` here does
        NOT dispatch ``ClientUnreachable`` (unlike the search tasks). The E-D5 taxonomy files
        this event under SEARCH only; the download loop is single-client and the label
        ``client=...`` would be meaningless (counter shared with the search workers). The
        unavailability is handled by the next cycle's retry + the warning log. Intentional
        asymmetry.
        """
        # Step 0 - SNAPSHOT: client I/O → unreachable or refused = dead daemon = ABORT.
        try:
            listed_statuses = await self._download_client.downloads()
        except _UNAVAILABLE as error:
            self._logger.warning(
                "download daemon unreachable (%s): iteration skipped, retry", error
            )
            return
        listed_files = frozenset(status.file for status in listed_statuses)
        # Clamped at 0: a nascent download (total not known yet) must not invent free space.
        outstanding_bytes = sum(
            max(status.size_bytes - status.bytes_done, 0) for status in listed_statuses
        )
        # Steps 1, 2 and 2b - STATES, COMPLETIONS, PRESENCE + LOSS: only StoreError, isolated.
        await self._download_tracker.track(listed_statuses, node_id=node_id)
        # Step 3 - CANDIDATES: NO client I/O → a StoreError or the disk's OSError, isolated (I2).
        try:
            await self._download_decider.queue_new_candidates(outstanding_bytes, node_id=node_id)
        except StoreError as error:
            self._logger.error(
                "download candidates store failure (%s): step skipped, continues", error
            )
        except OSError as error:
            # A missing or unreadable output mount: refuse to admit anything rather than take
            # down the crawler, which also catalogues. Conservative, loud, and retried next cycle.
            self._logger.error(
                "output directory unmeasurable (%s): no candidate admitted, retry", error
            )
        # Step 4 - START: client I/O → ClientUnreachableError = dead daemon = ABORT. Re-reads
        # ``read_tracked_states`` FRESHLY, so it runs even if step 3 partially failed.
        try:
            await self._download_starter.start_unlisted(listed_files)
        except ClientUnreachableError as error:
            self._logger.warning(
                "download daemon unreachable (%s): iteration skipped, retry", error
            )
            return
        except StoreError as error:
            self._logger.error("download start store failure (%s): step skipped, retry", error)
        # Step 5 - SOURCES: last, since it only observes; its failure must not skip a start (D8).
        try:
            await self._source_watcher.record_sources(listed_statuses, node_id=node_id)
        except _UNAVAILABLE as error:
            self._logger.warning("download daemon unreachable (%s): sources skipped, retry", error)
        except StoreError as error:
            self._logger.error("download sources store failure (%s): step skipped, retry", error)
