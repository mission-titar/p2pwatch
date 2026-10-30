"""What an image's SBOM lists for the premises: dpkg packages, components declared by hand."""

from dataclasses import dataclass


@dataclass(kw_only=True, frozen=True)
class DpkgPackage:
    name: str
    version: str


@dataclass(kw_only=True, frozen=True)
class DeclaredComponent:
    name: str
    version: str
