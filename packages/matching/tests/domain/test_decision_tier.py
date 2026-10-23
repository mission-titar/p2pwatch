from catalog_matching.domain.decision_tier import DecisionTier


def test_values_are_the_strings_of_the_policy_and_the_rows() -> None:
    assert {tier.value for tier in DecisionTier} == {"catalog", "notify", "download"}


def test_rank_orders_download_above_notify_above_catalog() -> None:
    assert DecisionTier.DOWNLOAD.rank > DecisionTier.NOTIFY.rank > DecisionTier.CATALOG.rank
