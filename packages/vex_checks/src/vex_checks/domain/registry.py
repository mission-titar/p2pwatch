"""The authoritative advisory to premise mapping.

Every OpenVEX ``not_affected`` claim we publish is anchored here to exactly one
premise descriptor. The keys are advisory identifiers (CVE or GHSA); the values are
the falsifiable premise each claim rests on.
"""

from vex_checks.domain.descriptors import DeclaredMinVersion, ModuleNotImported, Premise

PREMISES: dict[str, Premise] = {
    "CVE-2006-2691": DeclaredMinVersion("amule", "2.1.2"),
    "CVE-2006-2692": DeclaredMinVersion("amule", "2.1.2"),
    "CVE-2025-15366": ModuleNotImported("imaplib"),
    "CVE-2025-15367": ModuleNotImported("poplib"),
}
