"""The image premises: each one falsifiable fact behind a VEX ``not_affected`` claim, about the
packages of an image (dpkg packages, or components declared by hand like aMule)."""

from dataclasses import dataclass


@dataclass(kw_only=True, frozen=True)
class DpkgPackageAbsent:
    package: str


@dataclass(kw_only=True, frozen=True)
class DpkgMinVersion:
    package: str
    minimum: str


@dataclass(kw_only=True, frozen=True)
class DeclaredMinVersion:
    component: str
    minimum: str


ImagePremise = DpkgPackageAbsent | DpkgMinVersion | DeclaredMinVersion
