from amule_bump.application.ports.driven.upstream_client import UpstreamClient
from amule_bump.domain.git_object import GitObject


class FakeUpstreamClient(UpstreamClient):
    """An upstream repo served from dicts; a file absent from them reads as empty."""

    def __init__(
        self,
        *,
        latest_release_tag: str = "",
        tag_targets_by_tag: dict[str, GitObject] | None = None,
        annotated_tag_targets_by_object_id: dict[str, GitObject] | None = None,
        file_texts_by_ref_and_path: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self._latest_release_tag = latest_release_tag
        self._tag_targets_by_tag = tag_targets_by_tag or {}
        self._annotated_tag_targets_by_object_id = annotated_tag_targets_by_object_id or {}
        self._file_texts_by_ref_and_path = file_texts_by_ref_and_path or {}

    def read_latest_release_tag(self) -> str:
        return self._latest_release_tag

    def read_tag_target(self, tag: str) -> GitObject:
        return self._tag_targets_by_tag[tag]

    def read_annotated_tag_target(self, object_id: str) -> GitObject:
        return self._annotated_tag_targets_by_object_id[object_id]

    def read_file(self, ref: str, path: str) -> str:
        return self._file_texts_by_ref_and_path.get((ref, path), "")
