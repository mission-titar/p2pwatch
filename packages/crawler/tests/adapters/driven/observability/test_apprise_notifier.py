"""Apprise notifier: groups built per node_id on its first notification, add(url, tag) into
them, node_id in the title, routes by tag, writes each kind's Markdown and notify type,
mentions neutralised, a relayed log line sent untitled."""

from datetime import timedelta

import apprise
import pytest
from apprise.plugins.discord import USER_ROLE_DETECTION_RE

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import (
    CompletedDownload,
    Notification,
    RelayedLogLine,
    SourceAlert,
    SourceAlertKind,
    TierRise,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.source import SourceKey
from tests.fakes.adapters.driven.fake_apprise import FakeApprise

_NODE_ID = NodeId("titar-node-1")
_HASH = "8f3a1c0b9e7d44a2b6c1f0e9d8a7b6c5"
_SOURCE = SourceKey(Network.ED2K, "1f2e3d4c" * 4)
_062A = TargetTitle(TargetId("062A"), "Les demoiselles cambrioleuses")
_062B = TargetTitle(TargetId("062B"), "Le grand combat sous-marin")
_LINE = RelayedLogLine("online", Severity.INFO, _NODE_ID)


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


async def _sent_to_the_bare_group(notification: Notification) -> dict[str, object]:
    """What the bare group, whose title has no node prefix, sends for ``notification``."""
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, notification)
    [call] = groups[1].sent
    return call


def _rise(tier: DecisionTier, filename: str = "Keroro 062.avi") -> TierRise:
    link = f"ed2k://|file|Keroro%20062.avi|367185920|{_HASH}|/"
    return TierRise(tier, (_062A, _062B), filename, 367_185_920, link, _NODE_ID)


def _source_alert(
    source_name: str | None,
    absent_for: timedelta | None,
    target_titles: tuple[TargetTitle, ...] = (_062A,),
    filename: str = "Keroro 062.avi",
) -> SourceAlert:
    kind = SourceAlertKind.FIRST_USEFUL if absent_for is None else SourceAlertKind.REAPPEARED
    return SourceAlert(kind, _SOURCE, source_name, absent_for, target_titles, filename, _NODE_ID)


@pytest.mark.asyncio
async def test_targets_are_added_with_tags_to_the_prefixed_or_the_bare_group() -> None:
    notifier, groups = _notifier()
    assert groups == []  # nothing built before a notification names its node
    await notifier.notify(Audience.COMMUNITY, _LINE)
    prefixed, bare = groups
    assert prefixed.added == [("discord://x", "community"), ("discord://y", "operations")]
    assert bare.added == [("discord://z", "community")]


@pytest.mark.asyncio
async def test_both_groups_name_the_node_and_send_no_image() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, _LINE)
    for asset in (group.asset for group in groups):
        assert asset.app_id == "p2pwatch - titar-node-1"
        assert asset.app_url == "https://github.com/mission-titar/p2pwatch"
        assert asset.image_url(apprise.NotifyType.INFO) is None
        assert asset.image_url(apprise.NotifyType.INFO, logo=True) is None


@pytest.mark.asyncio
async def test_a_node_keeps_its_groups_and_another_node_gets_its_own() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, _LINE)
    await notifier.notify(Audience.COMMUNITY, _LINE)
    await notifier.notify(
        Audience.COMMUNITY, CompletedDownload((_062A,), "Keroro 062.avi", NodeId("titar-node-2"))
    )
    assert [group.asset.app_id for group in groups] == [
        "p2pwatch - titar-node-1",
        "p2pwatch - titar-node-1",
        "p2pwatch - titar-node-2",
        "p2pwatch - titar-node-2",
    ]
    assert [len(group.sent) for group in groups] == [2, 2, 1, 1]
    assert [call["title"] for call in groups[2].sent] == ["[titar-node-2] ✅ Downloaded"]


@pytest.mark.asyncio
async def test_the_node_prefix_goes_into_the_title_of_the_prefixed_group_only() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.COMMUNITY, _rise(DecisionTier.DOWNLOAD))
    await notifier.notify(Audience.COMMUNITY, _LINE)
    prefixed, bare = groups
    assert [(c["tag"], c["title"]) for c in prefixed.sent + bare.sent] == [
        ("community", "[titar-node-1] 📥 Download"),
        ("community", "[titar-node-1]"),
        ("community", "📥 Download"),
        ("community", ""),
    ]
    assert [c["body"] for c in prefixed.sent] == [c["body"] for c in bare.sent]
    assert bare.sent[1]["body"] == "online"


@pytest.mark.asyncio
async def test_every_message_is_sent_as_markdown() -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.OPERATIONS, RelayedLogLine("x", Severity.WARNING, _NODE_ID))
    calls = [call for group in groups for call in group.sent]
    assert [c["body_format"] for c in calls] == [apprise.NotifyFormat.MARKDOWN] * 2


@pytest.mark.asyncio
async def test_no_mention_reaches_apprise() -> None:
    hostile = "@everyone @here <@123> <@&456>"
    notifier, groups = _notifier()
    alert = _source_alert(hostile, None, (TargetTitle(TargetId("062A"), hostile),), hostile)
    await notifier.notify(Audience.COMMUNITY, alert)
    await notifier.notify(Audience.OPERATIONS, RelayedLogLine(hostile, Severity.WARNING, _NODE_ID))
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
    ],
)
async def test_a_relayed_log_lines_severity_maps_to_a_notify_type(
    severity: Severity, notify_type: apprise.NotifyType
) -> None:
    notifier, groups = _notifier()
    await notifier.notify(Audience.OPERATIONS, RelayedLogLine("x", severity, _NODE_ID))
    assert groups[0].sent[-1]["notify_type"] == notify_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("notification", "notify_type"),
    [
        (_rise(DecisionTier.NOTIFY), apprise.NotifyType.INFO),
        (_source_alert(None, timedelta(hours=26)), apprise.NotifyType.INFO),
        (CompletedDownload((_062A,), "x.avi", _NODE_ID), apprise.NotifyType.SUCCESS),
    ],
    ids=["rise", "source-alert", "completed-download"],
)
async def test_each_community_kind_has_its_notify_type(
    notification: Notification, notify_type: apprise.NotifyType
) -> None:
    assert (await _sent_to_the_bare_group(notification))["notify_type"] == notify_type


@pytest.mark.asyncio
async def test_a_rise_names_its_tier_its_targets_its_file_and_its_link() -> None:
    call = await _sent_to_the_bare_group(_rise(DecisionTier.DOWNLOAD))
    assert call["title"] == "📥 Download"
    assert call["body"] == (
        "**Targets**\n"
        "062A - Les demoiselles cambrioleuses\n"
        "062B - Le grand combat sous-marin\n"
        "\n"
        "**File**\n"
        "350.2 MiB - `Keroro 062.avi`\n"
        "\n"
        "**ed2k**\n"
        f"`ed2k://|file|Keroro%20062.avi|367185920|{_HASH}|/`"
    )


@pytest.mark.asyncio
async def test_a_rise_to_notify_is_titled_notify() -> None:
    assert (await _sent_to_the_bare_group(_rise(DecisionTier.NOTIFY)))["title"] == "🔎 Notify"


@pytest.mark.asyncio
async def test_a_backtick_in_the_name_cannot_close_its_code_span() -> None:
    # Discord pings a mention outside code: a name must not escape its span.
    call = await _sent_to_the_bare_group(_rise(DecisionTier.DOWNLOAD, "a`@everyone`b.avi"))
    body = call["body"]
    assert isinstance(body, str)
    assert "\n350.2 MiB - `a'@everyone'b.avi`\n".replace("@", "@\u200b") in body


@pytest.mark.asyncio
async def test_a_completed_download_names_its_targets_and_file() -> None:
    completed = CompletedDownload((_062A, _062B), "Keroro `062`.avi", _NODE_ID)
    call = await _sent_to_the_bare_group(completed)
    assert (call["title"], call["body"]) == (
        "✅ Downloaded",
        "**Targets**\n"
        "062A - Les demoiselles cambrioleuses\n"
        "062B - Le grand combat sous-marin\n"
        "\n"
        "**File**\n"
        "`Keroro '062'.avi`",
    )


@pytest.mark.asyncio
async def test_a_completed_download_without_a_target_names_none() -> None:
    call = await _sent_to_the_bare_group(CompletedDownload((), "Keroro 062.avi", _NODE_ID))
    assert call["body"] == "**Targets**\nunknown\n\n**File**\n`Keroro 062.avi`"


@pytest.mark.asyncio
async def test_a_first_useful_source_names_itself_its_targets_and_its_file() -> None:
    call = await _sent_to_the_bare_group(_source_alert("AnimuseeFMR", None))
    assert (call["title"], call["body"]) == (
        "📥 Source useful for the first time",
        "**Source**\n`AnimuseeFMR` 1f2e3d4c…, useful for the first time\n\n"
        "**Targets**\n062A - Les demoiselles cambrioleuses\n\n"
        "**File**\n`Keroro 062.avi`",
    )


@pytest.mark.asyncio
async def test_a_reappeared_source_says_how_long_it_was_absent() -> None:
    call = await _sent_to_the_bare_group(_source_alert("AnimuseeFMR", timedelta(hours=26)))
    assert (call["title"], call["body"]) == (
        "🔁 Source reappeared",
        "**Source**\n`AnimuseeFMR` 1f2e3d4c…, reappeared after 26 h\n\n"
        "**Targets**\n062A - Les demoiselles cambrioleuses\n\n"
        "**File**\n`Keroro 062.avi`",
    )


@pytest.mark.asyncio
async def test_a_source_without_a_name_or_a_target_names_its_hash_and_its_file() -> None:
    call = await _sent_to_the_bare_group(_source_alert(None, None, ()))
    assert call["body"] == (
        "**Source**\n1f2e3d4c…, useful for the first time\n\n**File**\n`Keroro 062.avi`"
    )


@pytest.mark.asyncio
async def test_a_backtick_in_a_source_name_cannot_close_its_code_span() -> None:
    alert = _source_alert("a`@everyone`b", timedelta(seconds=43_200.000001), (), "x.avi")
    body = (await _sent_to_the_bare_group(alert))["body"]
    assert isinstance(body, str)
    assert body.startswith(
        "**Source**\n`a'@everyone'b` 1f2e3d4c…, reappeared after 12 h\n".replace("@", "@\u200b")
    )


@pytest.mark.asyncio
async def test_a_real_apprise_with_no_url_notifies_nothing() -> None:
    notifier = AppriseNotifier((), apprise_factory=apprise.Apprise)
    await notifier.notify(Audience.COMMUNITY, _LINE)  # does not raise
