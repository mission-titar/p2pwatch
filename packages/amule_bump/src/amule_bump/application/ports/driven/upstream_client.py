from abc import ABC, abstractmethod

from amule_bump.domain.git_object import GitObject


class UpstreamClient(ABC):
    """Reads one git repository: its latest release, its tags and its files at a ref."""

    @abstractmethod
    def read_latest_release_tag(self) -> str:
        """The tag of the repository's latest release."""

    @abstractmethod
    def read_tag_target(self, tag: str) -> GitObject:
        """What the tag's ref names: an annotated tag object, or a lightweight tag's commit."""

    @abstractmethod
    def read_annotated_tag_target(self, object_id: str) -> GitObject:
        """The object the annotated tag object ``object_id`` names."""

    @abstractmethod
    def read_file(self, ref: str, *, path: str) -> str:
        """The file's text at ``ref``, empty when the file is absent there."""
