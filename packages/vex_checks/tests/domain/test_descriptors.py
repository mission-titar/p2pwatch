from typing import get_args

from vex_checks.domain.descriptors import (
    JUSTIFICATION_BY_FAMILY,
    DeclaredMinVersion,
    DpkgMinVersion,
    DpkgPackageAbsent,
    ImagePremise,
    ModuleNotImported,
    Premise,
    ProgramNeverInvoked,
    SourcePremise,
    family,
    is_image_premise,
    is_source_premise,
)


def test_source_descriptors_report_source_family() -> None:
    for premise in (ModuleNotImported("tarfile"), ProgramNeverInvoked("ffmpeg")):
        assert family(premise) == "source"


def test_image_descriptors_report_image_family() -> None:
    for premise in (
        DpkgPackageAbsent("nghttp2"),
        DpkgMinVersion("clamav", "0.99"),
        DeclaredMinVersion("amule", "2.1.2"),
    ):
        assert family(premise) == "image"


def test_justification_by_family_is_closed() -> None:
    assert JUSTIFICATION_BY_FAMILY == {
        "source": "vulnerable_code_not_in_execute_path",
        "image": "vulnerable_code_not_present",
    }


def test_premise_union_covers_both_families() -> None:
    assert set(get_args(Premise)) == set(get_args(SourcePremise)) | set(get_args(ImagePremise))


def test_is_source_premise_matches_only_the_source_family() -> None:
    assert is_source_premise(ModuleNotImported("tarfile")) is True
    assert is_source_premise(DpkgPackageAbsent("nghttp2")) is False


def test_is_image_premise_matches_only_the_image_family() -> None:
    assert is_image_premise(DpkgPackageAbsent("nghttp2")) is True
    assert is_image_premise(ModuleNotImported("tarfile")) is False
