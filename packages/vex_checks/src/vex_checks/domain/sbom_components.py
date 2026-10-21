"""What an image's SBOM lists for the premises: dpkg packages, components declared by hand."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DpkgPackage:
    name: str
    version: str


@dataclass(frozen=True)
class DeclaredComponent:
    name: str
    version: str
