"""Premise descriptors, their two families, and the ``family`` classifier.

A premise is a small frozen dataclass naming one falsifiable fact behind a VEX
``not_affected`` claim (e.g. "``tarfile`` is never imported"). Premises split
into two families: ``source`` premises assert something about our own code path,
``image`` premises assert something about the packages present in the image (dpkg
packages, or components declared by hand like aMule).
"""

from dataclasses import dataclass
from typing import Literal, TypeIs, assert_never


@dataclass(frozen=True)
class ModuleNotImported:
    module: str


@dataclass(frozen=True)
class DpkgPackageAbsent:
    package: str


@dataclass(frozen=True)
class DpkgMinVersion:
    package: str
    minimum: str


@dataclass(frozen=True)
class DeclaredMinVersion:
    component: str
    minimum: str


SourcePremise = ModuleNotImported
ImagePremise = DpkgPackageAbsent | DpkgMinVersion | DeclaredMinVersion
Premise = SourcePremise | ImagePremise

Family = Literal["source", "image"]

JUSTIFICATION_BY_FAMILY: dict[Family, str] = {
    "source": "vulnerable_code_not_in_execute_path",
    "image": "vulnerable_code_not_present",
}


def family(premise: Premise) -> Family:
    match premise:
        case ModuleNotImported():
            return "source"
        case DpkgPackageAbsent() | DpkgMinVersion() | DeclaredMinVersion():
            return "image"
        case _:  # pragma: no cover
            assert_never(premise)


def is_image_premise(premise: Premise) -> TypeIs[ImagePremise]:
    return family(premise) == "image"
