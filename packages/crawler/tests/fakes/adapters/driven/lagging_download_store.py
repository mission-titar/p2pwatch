from p2pwatch.domain.file_key import FileKey
from tests.fakes.adapters.driven.fake_download_store import FakeDownloadStore


class LaggingDownloadStore(FakeDownloadStore):
    """Untracked whenever asked, as if each row had been queued since by another writer."""

    def is_tracked(self, file: FileKey) -> bool:
        return False
