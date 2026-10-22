"""Apprise notifier: groups built per node_id on its first notification, add(url, tag) into
them, node_id in the title, routes by tag, maps NotifyType, sends markdown, mentions neutralised."""

import apprise
import pytest
from apprise.plugins.discord import USER_ROLE_DETECTION_RE

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.domain.observability.policy import Audience, Severity
from tests.fakes.adapters.driven.fake_apprise import FakeApprise

_NODE = "titar-node-1"


def _notifier() -> tuple[AppriseNotifier, list[FakeApprise]]:
    """The notifier and every apprise group it builds, in order."""
    targets = (
        ("discord://x", Audience.COMMUNITY, True),
        ("discord://y", Audience.OPERATIONS, True),
        ("discord://z", Audience.COMMUNITY, False),
    )
    groups: list[FakeApprise] = []

    def factory(asset: apprise.AppriseAsset) -> FakeApprise:
        groups.append(FakeApprise(asset))
        return groups[-1]

    return AppriseNotifier(targets, apprise_factory=factory), groups


@pytest.mark.asyncio
async def test_targets_are_added_with_tags_to_the_prefixed_or_the_bare_group() -> None:
    notifier, groups = _notifier()
    assert groups == []  # nothing built before a notification names its node
    await notifier.notify(Audience.COMMUNITY, "t", "x", Severity.INFO, _NODE)
    prefixed, bare = groups
    assert prefixed.added == [("discord://x", "community"), ("discord://y", "operations")]
    assert bare.added == [("discord://z", "community")]


@pytest.mark.asyncio
async def test_both_groups_name_the_node_and_send_no_image() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, "t", "x", Severity.INFO, _NODE)
    for asset in (group.asset for group in groups):
        assert asset.app_id == "p2pwatch - titar-node-1"
        assert asset.app_url == "https://github.com/mission-titar/p2pwatch"
        assert asset.image_url(apprise.NotifyType.INFO) is None
        assert asset.image_url(apprise.NotifyType.INFO, logo=True) is None


@pytest.mark.asyncio
async def test_a_node_keeps_its_groups_and_another_node_gets_its_own() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, "t", "x", Severity.INFO, _NODE)
    await notifier.notify(Audience.COMMUNITY, "t", "x", Severity.INFO, _NODE)
    await notifier.notify(Audience.COMMUNITY, "t", "x", Severity.INFO, "titar-node-2")
    assert [group.asset.app_id for group in groups] == [
        "p2pwatch - titar-node-1",
        "p2pwatch - titar-node-1",
        "p2pwatch - titar-node-2",
        "p2pwatch - titar-node-2",
    ]
    assert [len(group.sent) for group in groups] == [2, 2, 1, 1]
    assert [call["title"] for call in groups[2].sent] == ["[titar-node-2] t"]


@pytest.mark.asyncio
async def test_the_node_prefix_goes_into_the_title_of_the_prefixed_group_only() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, "📥 Download", "body", Severity.INFO, _NODE)
    await notifier.notify(Audience.COMMUNITY, "", "online", Severity.INFO, _NODE)
    prefixed, bare = groups
    assert [(c["tag"], c["title"], c["body"]) for c in prefixed.sent + bare.sent] == [
        ("community", "[titar-node-1] 📥 Download", "body"),
        ("community", "[titar-node-1]", "online"),
        ("community", "📥 Download", "body"),
        ("community", "", "online"),
    ]


@pytest.mark.asyncio
async def test_every_message_is_sent_as_markdown() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.OPERATIONS, "", "x", Severity.WARNING, _NODE)
    calls = [call for group in groups for call in group.sent]
    assert [c["body_format"] for c in calls] == [apprise.NotifyFormat.MARKDOWN] * 2


@pytest.mark.asyncio
async def test_no_mention_reaches_apprise() -> None:
    hostile = "@everyone @here <@123> <@&456>"
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, hostile, hostile, Severity.INFO, _NODE)
    for call in (call for group in groups for call in group.sent):
        for text in (call["title"], call["body"]):
            assert isinstance(text, str)
            assert USER_ROLE_DETECTION_RE.search(text) is None, text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("severity", "notify_type"),
    [
        (Severity.INFO, apprise.NotifyType.INFO),
        (Severity.SUCCESS, apprise.NotifyType.SUCCESS),
        (Severity.WARNING, apprise.NotifyType.WARNING),
        (Severity.ERROR, apprise.NotifyType.FAILURE),
    ],
)
async def test_severity_maps_to_a_notify_type(
    severity: Severity, notify_type: apprise.NotifyType
) -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.OPERATIONS, "", "x", severity, _NODE)
    assert groups[0].sent[-1]["notify_type"] == notify_type


@pytest.mark.asyncio
async def test_a_real_apprise_with_no_url_notifies_nothing() -> None:
    notifier = AppriseNotifier((), apprise_factory=apprise.Apprise)
    await notifier.notify(Audience.COMMUNITY, "t", "x", Severity.INFO, "n")  # does not raise
