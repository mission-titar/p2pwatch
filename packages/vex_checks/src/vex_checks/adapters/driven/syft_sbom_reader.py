import json
from pathlib import Path, PurePath

from vex_checks.application.ports.driven.sbom_reader import SbomReader
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage


class SyftSbomReader(SbomReader):
    """A Syft JSON SBOM at the path each call is given."""

    def read_dpkg_packages(self, sbom_path: PurePath) -> list[DpkgPackage]:
        # Syft types those "deb": aMule, declared by hand, and our Python wheels are not dpkg's.
        return [
            DpkgPackage(name=artifact["name"], version=artifact["version"])
            for artifact in _read_artifacts(sbom_path)
            if artifact["type"] == "deb"
        ]

    def read_declared_components(self, sbom_path: PurePath) -> list[DeclaredComponent]:
        # A hand-declared artifact has a ``pkg:generic/`` purl, apart from dpkg names.
        return [
            DeclaredComponent(name=artifact["name"], version=artifact["version"])
            for artifact in _read_artifacts(sbom_path)
            if artifact.get("purl", "").startswith("pkg:generic/")
        ]


def _read_artifacts(sbom_path: PurePath) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = json.loads(Path(sbom_path).read_text())["artifacts"]
    return artifacts
