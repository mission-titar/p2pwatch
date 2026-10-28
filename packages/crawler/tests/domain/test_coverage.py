from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.coverage import TargetCoverageStatus, coverage_of


def test_no_decision_is_none() -> None:
    status = coverage_of(TargetId("062A"), [])
    assert status.target_id == "062A"
    assert status.status is TargetCoverageStatus.NONE
    assert status.best_tier is None
    assert status.file_count == 0


def test_download_tier_is_found() -> None:
    """Mixed case: the catalog-tier decision is excluded, so only the ``download`` file counts."""
    status = coverage_of(TargetId("062A"), [DecisionTier.DOWNLOAD, DecisionTier.CATALOG])
    assert status.status is TargetCoverageStatus.FOUND
    assert status.best_tier is DecisionTier.DOWNLOAD
    assert status.file_count == 1


def test_only_weak_tiers_is_partial() -> None:
    status = coverage_of(TargetId("062A"), [DecisionTier.CATALOG, DecisionTier.NOTIFY])
    assert status.status is TargetCoverageStatus.PARTIAL
    assert status.best_tier is DecisionTier.NOTIFY
    assert status.file_count == 1


def test_only_catalog_tier_is_none() -> None:
    """Catalog-tier decisions are the ``keroro_large`` catch-all: any unidentified keroro file
    with no numeric token resolves to the smallest target_id (``001A``) via the engine
    tie-break. They must NOT count as coverage of an episode, so a target whose only decisions
    are catalog-tier reads none/0 (mirrors the ``/files`` "unidentified" mask)."""
    status = coverage_of(TargetId("062A"), [DecisionTier.CATALOG, DecisionTier.CATALOG])
    assert status.status is TargetCoverageStatus.NONE
    assert status.best_tier is None
    assert status.file_count == 0


def test_status_values_are_the_dashboard_words() -> None:
    assert [status.value for status in TargetCoverageStatus] == ["found", "partial", "none"]
