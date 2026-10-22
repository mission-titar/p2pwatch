import json
import re
from collections.abc import Callable
from pathlib import Path, PurePath

import pytest

from vex_checks.adapters.driven.syft_sbom_reader import SyftSbomReader
from vex_checks.domain.broken_input_error import BrokenInputError
from vex_checks.domain.sbom_components import DeclaredComponent, DpkgPackage


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
    read: Callable[[PurePath], object], tmp_path: Path
) -> None:
    sbom_path = tmp_path / "absent.syft.json"

    with pytest.raises(BrokenInputError, match=f"^{re.escape(str(sbom_path))}: no such file$"):
        read(sbom_path)
