import json
from dataclasses import astuple, dataclass
from pathlib import Path, PurePath

from vex_checks.application.ports.driven.sbom_reader import SbomReader
from vex_checks.domain.broken_input_error import BrokenInputError
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage


class SyftSbomReader(SbomReader):
    """A Syft JSON SBOM at the path each call is given."""

    def read_dpkg_packages(self, sbom_path: PurePath) -> list[DpkgPackage]:
        # Syft types those "deb": aMule, declared by hand, and our Python wheels are not dpkg's.
        return [
            DpkgPackage(name=artifact.name, version=artifact.version)
            for artifact in _read_artifacts(sbom_path)
            if artifact.type == "deb"
        ]

    def read_declared_components(self, sbom_path: PurePath) -> list[DeclaredComponent]:
        # A hand-declared artifact has a ``pkg:generic/`` purl, apart from dpkg names.
        return [
            DeclaredComponent(name=artifact.name, version=artifact.version)
            for artifact in _read_artifacts(sbom_path)
            if artifact.purl.startswith("pkg:generic/")
        ]


@dataclass(frozen=True)
class _SyftArtifact:
    type: str
    name: str
    version: str
    purl: str


def _read_artifacts(sbom_path: PurePath) -> list[_SyftArtifact]:
    try:
        document = json.loads(Path(sbom_path).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BrokenInputError(f"{sbom_path}: no such file") from error
    except OSError as error:
        raise BrokenInputError(f"{sbom_path}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise BrokenInputError(f"{sbom_path}: not UTF-8") from error
    except json.JSONDecodeError as error:
        raise BrokenInputError(f"{sbom_path}: not JSON") from error
    try:
        artifacts = [
            _SyftArtifact(
                type=artifact["type"],
                name=artifact["name"],
                version=artifact["version"],
                purl=artifact.get("purl", ""),
            )
            for artifact in document["artifacts"]
        ]
    except (KeyError, TypeError, AttributeError) as error:
        raise BrokenInputError(f"{sbom_path}: not a Syft JSON SBOM") from error
    # JSON can hold a number where Syft writes a string, which a later filter would choke on.
    if not all(isinstance(field, str) for artifact in artifacts for field in astuple(artifact)):
        raise BrokenInputError(f"{sbom_path}: not a Syft JSON SBOM")
    return artifacts
