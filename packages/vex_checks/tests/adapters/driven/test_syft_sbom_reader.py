import json
import re
from pathlib import Path, PurePath
from typing import Protocol

import pytest

from vex_checks.adapters.driven.syft_sbom_reader import SyftSbomReader
from vex_checks.domain.broken_input_error import BrokenInputError
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage


class SbomRead(Protocol):
    def __call__(self, sbom_path: PurePath, /) -> object: ...


def _write_sbom(tmp_path: Path, artifacts: list[dict[str, str]]) -> Path:
    path = tmp_path / "sbom.syft.json"
    path.write_text(json.dumps({"artifacts": artifacts}))
    return path


def test_read_dpkg_packages_keeps_only_deb_artifacts(tmp_path: Path) -> None:
    # aMule is compiled by us and declared by hand, so Syft types it "UnknownPackage", not "deb".
    path = _write_sbom(
        tmp_path,
        [
            {"type": "deb", "name": "libcurl4t64", "version": "8.14.1-2"},
            {"type": "deb", "name": "zlib1g", "version": "1:1.3.dfsg+really1.3.1-1"},
            {"type": "UnknownPackage", "name": "amule", "version": "3.1.0"},
            {"type": "python", "name": "packaging", "version": "24.0"},
        ],
    )
    assert SyftSbomReader().read_dpkg_packages(path) == [
        DpkgPackage("libcurl4t64", "8.14.1-2"),
        DpkgPackage("zlib1g", "1:1.3.dfsg+really1.3.1-1"),
    ]


def test_read_declared_components_keeps_only_generic_purl_artifacts(tmp_path: Path) -> None:
    # The real shape of the hand-declared aMule artifact, as Syft 1.52 emits it.
    path = _write_sbom(
        tmp_path,
        [
            {
                "type": "UnknownPackage",
                "name": "amule",
                "version": "3.1.0",
                "purl": "pkg:generic/amule@3.1.0",
            },
            {
                "type": "deb",
                "name": "amule",
                "version": "1:2.3.3-3",
                "purl": "pkg:deb/debian/amule@1:2.3.3-3",
            },
            {"type": "python", "name": "packaging", "version": "24.0"},
        ],
    )
    assert SyftSbomReader().read_declared_components(path) == [DeclaredComponent("amule", "3.1.0")]


@pytest.mark.parametrize(
    "read",
    [SyftSbomReader().read_dpkg_packages, SyftSbomReader().read_declared_components],
    ids=["dpkg-packages", "declared-components"],
)
def test_reading_an_absent_sbom_raises_a_broken_input_naming_it(
    read: SbomRead, tmp_path: Path
) -> None:
    sbom_path = tmp_path / "absent.syft.json"

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(sbom_path))}: no such file$"):
        read(sbom_path)


_READS = pytest.mark.parametrize(
    "read",
    [SyftSbomReader().read_dpkg_packages, SyftSbomReader().read_declared_components],
    ids=["dpkg-packages", "declared-components"],
)


@_READS
def test_reading_a_directory_raises_a_broken_input_naming_it(
    read: SbomRead, tmp_path: Path
) -> None:
    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(tmp_path))}: Is a directory$"):
        read(tmp_path)


@_READS
def test_reading_an_sbom_not_in_utf_8_raises_a_broken_input_naming_it(
    read: SbomRead, tmp_path: Path
) -> None:
    sbom_path = tmp_path / "sbom.syft.json"
    sbom_path.write_bytes(b'{"artifacts": "\xe9"}')

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(sbom_path))}: not UTF-8$"):
        read(sbom_path)


@_READS
def test_reading_an_sbom_not_in_json_raises_a_broken_input_naming_it(
    read: SbomRead, tmp_path: Path
) -> None:
    sbom_path = tmp_path / "sbom.syft.json"
    sbom_path.write_text("{")

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(sbom_path))}: not JSON$"):
        read(sbom_path)


@_READS
@pytest.mark.parametrize(
    "document",
    [
        {},
        {"artifacts": 3},
        {"artifacts": ["amule"]},
        {"artifacts": [{"type": "deb", "name": "zlib1g"}]},
        {"artifacts": [{"type": "deb", "name": "zlib1g", "version": "1", "purl": 3}]},
    ],
    ids=["no-artifacts", "artifacts-not-a-list", "artifact-not-an-object", "no-version", "purl"],
)
def test_reading_a_json_not_a_syft_sbom_raises_a_broken_input_naming_it(
    read: SbomRead, document: object, tmp_path: Path
) -> None:
    sbom_path = tmp_path / "sbom.syft.json"
    sbom_path.write_text(json.dumps(document))

    with pytest.raises(
        BrokenInputError, match=f"^{re.escape(str(sbom_path))}: not a Syft JSON SBOM$"
    ):
        read(sbom_path)
