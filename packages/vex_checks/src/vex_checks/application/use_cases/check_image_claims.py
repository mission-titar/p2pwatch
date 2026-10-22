"""Checks a VEX's image claims: the image premises it claims, against a built image's SBOM."""

import dataclasses
from collections.abc import Mapping
from pathlib import PurePath

from vex_checks.application.ports.driven.sarif_writer import SarifWriter
from vex_checks.application.ports.driven.sbom_reader import SbomReader
from vex_checks.application.ports.driven.vex_reader import VexReader
from vex_checks.application.ports.driving.image_claims_checker import (
    ImageClaimsChecker,
    ImageClaimsReport,
)
from vex_checks.domain.descriptors import ImagePremise
from vex_checks.domain.image_premises import evaluate_image_premises
from vex_checks.domain.vex_location import locate_vex

_RULE_ID = "unsatisfied-image-claim"


class CheckImageClaims(ImageClaimsChecker):
    """Over the registry's premises, naming a VEX inside ``repo_root`` relative to it."""

    def __init__(
        self,
        *,
        premises: Mapping[str, ImagePremise],
        repo_root: PurePath,
        vex_reader: VexReader,
        sbom_reader: SbomReader,
        sarif_writer: SarifWriter,
    ) -> None:
        self._premises = premises
        self._repo_root = repo_root
        self._vex_reader = vex_reader
        self._sbom_reader = sbom_reader
        self._sarif_writer = sarif_writer

    def check_image_claims(
        self, sbom_path: PurePath, vex_path: PurePath, sarif_path: PurePath | None
    ) -> ImageClaimsReport:
        claims = self._vex_reader.read_claims(vex_path)
        premises = {
            advisory_id: premise
            for advisory_id, premise in self._premises.items()
            if advisory_id in claims
        }
        vex_location = locate_vex(vex_path, self._repo_root)
        unlocated = evaluate_image_premises(
            premises,
            self._sbom_reader.read_dpkg_packages(sbom_path),
            self._sbom_reader.read_declared_components(sbom_path),
        )
        problems = tuple(
            dataclasses.replace(violation, location=vex_location) for violation in unlocated
        )
        if sarif_path is not None:
            self._sarif_writer.write_violations(sarif_path, _RULE_ID, problems, vex_location)
        return ImageClaimsReport(problems=problems)
