from vex_checks.domain.descriptors import DeclaredMinVersion
from vex_checks.domain.registry import PREMISES


def test_the_amuleweb_claims_rest_on_the_declared_amule_version() -> None:
    # Fixed in aMule 2.1.2; NVD's versionless CPE flags every later aMule too.
    for cve in ("CVE-2006-2691", "CVE-2006-2692"):
        assert PREMISES[cve] == DeclaredMinVersion("amule", "2.1.2")
