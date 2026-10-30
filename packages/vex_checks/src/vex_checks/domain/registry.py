"""The image premise each claim about an image's packages rests on, by advisory id (CVE or GHSA).
A claim about our code rests on a source rule instead."""

from vex_checks.domain.descriptors import DeclaredMinVersion, ImagePremise

PREMISES: dict[str, ImagePremise] = {
    "CVE-2006-2691": DeclaredMinVersion(component="amule", minimum="2.1.2"),
    "CVE-2006-2692": DeclaredMinVersion(component="amule", minimum="2.1.2"),
}
