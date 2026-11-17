"""Apprise notifier: each target URL a service named by its scheme and its audience, sent to
through an apprise object of its own per node, the node in the title of the services that ask
for it, each kind's Markdown and notify type, mentions neutralised, a relayed log line sent
untitled, any answer but a success a refusal."""

import socket
from datetime import timedelta

import apprise
import pytest
from apprise.plugins.discord import USER_ROLE_DETECTION_RE

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability.events import TargetTitle
from p2pwatch.domain.observability.notification import (
    CompletedDownload,
    Notification,
    RelayedLogLine,
    SourceAlert,
    SourceAlertKind,
    TierRise,
)
from p2pwatch.domain.observability.notification_sends import (
    NotificationRefusedError,
    NotificationService,
)
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.source import SourceKey
from tests.contracts.application.ports.driven.notifier_contract import NotifierContract
from tests.fakes.adapters.driven.fake_apprise import FakeApprise

_NODE_ID = NodeId("titar-node-1")
_HASH = "8f3a1c0b9e7d44a2b6c1f0e9d8a7b6c5"
_SOURCE = SourceKey(network=Network.ED2K, native_id="1f2e3d4c" * 4)
_062A = TargetTitle(target_id=TargetId("062A"), title="Les demoiselles cambrioleuses")
_062B = TargetTitle(target_id=TargetId("062B"), title="Le grand combat sous-marin")
_LINE = RelayedLogLine(message="online", severity=Severity.INFO, node_id=_NODE_ID)

# The services of ``_notifier``'s three URLs, in the order configured.
_DISCORD = NotificationService(scheme="discord", audience=Audience.COMMUNITY)
_NTFY = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)
_SECOND_DISCORD = NotificationService(scheme="discord", audience=Audience.COMMUNITY, ordinal=2)


def _notifier(
    status: apprise.AppriseResultStatus = apprise.AppriseResultStatus.SUCCESS,
) -> tuple[AppriseNotifier, list[FakeApprise]]:
    """The notifier and every apprise object it builds, in order, each answering ``status``; the
    third URL's titles go without the node's prefix."""
    targets = (
        ("discord://x", Audience.COMMUNITY, True),
        ("ntfy://y", Audience.OPERATIONS, True),
        ("discord://z", Audience.COMMUNITY, False),
    )
    built: list[FakeApprise] = []

    def factory(*, asset: apprise.AppriseAsset) -> FakeApprise:
        built.append(FakeApprise(asset=asset, status=status))
        return built[-1]

    return AppriseNotifier(targets, apprise_factory=factory), built


async def _sent_without_the_node_prefix(notification: Notification) -> dict[str, object]:
    """What the service whose title has no node prefix is sent for ``notification``."""
    notifier, built = _notifier()
    await notifier.notify(_SECOND_DISCORD, notification=notification)
    [call] = built[0].sent
    return call


def _rise(tier: DecisionTier, *, filename: str = "Keroro 062.avi") -> TierRise:
    return TierRise(
        tier=tier,
        target_titles=(_062A, _062B),
        file=FileKey(network=Network.ED2K, native_id=_HASH),
        filename=filename,
        size_bytes=367_185_920,
        node_id=_NODE_ID,
    )


def _source_alert(
    source_name: str | None,
    *,
    absent_for: timedelta | None,
    target_titles: tuple[TargetTitle, ...] = (_062A,),
    filename: str = "Keroro 062.avi",
) -> SourceAlert:
    kind = SourceAlertKind.FIRST_USEFUL if absent_for is None else SourceAlertKind.REAPPEARED
    return SourceAlert(
        kind=kind,
        source=_SOURCE,
        source_name=source_name,
        absent_for=absent_for,
        target_titles=target_titles,
        filename=filename,
        node_id=_NODE_ID,
    )


class TestAppriseNotifier(NotifierContract):
    def notifier(self) -> Notifier:
        return _notifier()[0]

    def refusing_notifier(self) -> Notifier:
        return _notifier(apprise.AppriseResultStatus.FAILURE)[0]


def test_each_url_is_a_service_named_by_its_scheme_and_audience_a_second_alike_by_its_ordinal() -> (
    None
):
    notifier, _ = _notifier()

    assert notifier.services() == (_DISCORD, _NTFY, _SECOND_DISCORD)


def test_a_scheme_is_read_in_lower_case_and_a_url_without_one_is_of_the_unknown_scheme() -> None:
    targets = (("Discord://x", Audience.COMMUNITY, True), ("a-token", Audience.OPERATIONS, True))

    services = AppriseNotifier(targets, apprise_factory=apprise.Apprise).services()

    assert [str(service) for service in services] == ["discord community", "unknown operations"]


def test_a_notifier_without_a_url_has_no_service() -> None:
    assert AppriseNotifier((), apprise_factory=apprise.Apprise).services() == ()


@pytest.mark.asyncio
async def test_each_service_is_sent_to_through_an_apprise_object_holding_its_url_alone() -> None:
    notifier, built = _notifier()
    built_before_a_notification = list(built)

    await notifier.notify(_SECOND_DISCORD, notification=_LINE)
    await notifier.notify(_DISCORD, notification=_LINE)

    assert built_before_a_notification == []
    assert [(apprise_object.added, len(apprise_object.sent)) for apprise_object in built] == [
        (["discord://z"], 1),
        (["discord://x"], 1),
    ]


@pytest.mark.asyncio
async def test_each_apprise_object_names_the_node_and_sends_no_image() -> None:
    notifier, built = _notifier()

    await notifier.notify(_DISCORD, notification=_LINE)
    await notifier.notify(_NTFY, notification=_LINE)

    for asset in (apprise_object.asset for apprise_object in built):
        assert asset.app_id == "p2pwatch - titar-node-1"
        assert asset.app_url == "https://github.com/mission-titar/p2pwatch"
        assert asset.image_url(apprise.NotifyType.INFO) is None
        assert asset.image_url(apprise.NotifyType.INFO, logo=True) is None


@pytest.mark.asyncio
async def test_a_node_keeps_its_apprise_object_per_service_and_another_node_gets_its_own() -> None:
    notifier, built = _notifier()
    other_node = CompletedDownload(
        target_titles=(_062A,), filename="Keroro 062.avi", node_id=NodeId("titar-node-2")
    )

    await notifier.notify(_DISCORD, notification=_LINE)
    await notifier.notify(_DISCORD, notification=_LINE)
    await notifier.notify(_DISCORD, notification=other_node)

    assert [(o.asset.app_id, len(o.sent)) for o in built] == [
        ("p2pwatch - titar-node-1", 2),
        ("p2pwatch - titar-node-2", 1),
    ]
    assert [call["title"] for call in built[1].sent] == ["[titar-node-2] ✅ Downloaded"]


@pytest.mark.asyncio
async def test_the_node_prefix_goes_into_the_title_of_the_services_that_ask_for_it() -> None:
    notifier, built = _notifier()

    await notifier.notify(_DISCORD, notification=_rise(DecisionTier.DOWNLOAD))
    await notifier.notify(_DISCORD, notification=_LINE)
    await notifier.notify(_SECOND_DISCORD, notification=_rise(DecisionTier.DOWNLOAD))
    await notifier.notify(_SECOND_DISCORD, notification=_LINE)

    prefixed, bare = built
    assert [call["title"] for call in prefixed.sent + bare.sent] == [
        "[titar-node-1] 📥 Download",
        "[titar-node-1]",
        "📥 Download",
        "",
    ]
    assert [call["body"] for call in prefixed.sent] == [call["body"] for call in bare.sent]
    assert bare.sent[1]["body"] == "online"


@pytest.mark.asyncio
async def test_every_message_is_sent_as_markdown() -> None:
    notifier, built = _notifier()

    await notifier.notify(
        _NTFY,
        notification=RelayedLogLine(message="x", severity=Severity.WARNING, node_id=_NODE_ID),
    )

    [call] = built[0].sent
    assert call["body_format"] == apprise.NotifyFormat.MARKDOWN


@pytest.mark.asyncio
async def test_no_mention_reaches_apprise() -> None:
    hostile = "@everyone @here <@123> <@&456>"
    notifier, built = _notifier()
    alert = _source_alert(
        hostile,
        absent_for=None,
        target_titles=(TargetTitle(target_id=TargetId("062A"), title=hostile),),
        filename=hostile,
    )

    await notifier.notify(_DISCORD, notification=alert)
    await notifier.notify(
        _NTFY,
        notification=RelayedLogLine(message=hostile, severity=Severity.WARNING, node_id=_NODE_ID),
    )

    for call in (call for apprise_object in built for call in apprise_object.sent):
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
    *, severity: Severity, notify_type: apprise.NotifyType
) -> None:
    notifier, built = _notifier()

    await notifier.notify(
        _NTFY, notification=RelayedLogLine(message="x", severity=severity, node_id=_NODE_ID)
    )

    assert built[0].sent[-1]["notify_type"] == notify_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("notification", "notify_type"),
    [
        (_rise(DecisionTier.NOTIFY), apprise.NotifyType.INFO),
        (_source_alert(None, absent_for=timedelta(hours=26)), apprise.NotifyType.INFO),
        (
            CompletedDownload(target_titles=(_062A,), filename="x.avi", node_id=_NODE_ID),
            apprise.NotifyType.SUCCESS,
        ),
    ],
    ids=["rise", "source-alert", "completed-download"],
)
async def test_each_community_kind_has_its_notify_type(
    *, notification: Notification, notify_type: apprise.NotifyType
) -> None:
    assert (await _sent_without_the_node_prefix(notification))["notify_type"] == notify_type


@pytest.mark.asyncio
async def test_a_rise_names_its_tier_its_targets_its_file_and_its_link() -> None:
    call = await _sent_without_the_node_prefix(_rise(DecisionTier.DOWNLOAD))
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
    assert (await _sent_without_the_node_prefix(_rise(DecisionTier.NOTIFY)))["title"] == "🔎 Notify"


@pytest.mark.asyncio
async def test_a_backtick_in_the_name_cannot_close_its_code_span() -> None:
    # Discord pings a mention outside code: a name must not escape its span.
    call = await _sent_without_the_node_prefix(
        _rise(DecisionTier.DOWNLOAD, filename="a`@everyone`b.avi")
    )
    body = call["body"]
    assert isinstance(body, str)
    assert "\n350.2 MiB - `a'@everyone'b.avi`\n".replace("@", "@\u200b") in body


@pytest.mark.asyncio
async def test_a_completed_download_names_its_targets_and_file() -> None:
    completed = CompletedDownload(
        target_titles=(_062A, _062B), filename="Keroro `062`.avi", node_id=_NODE_ID
    )
    call = await _sent_without_the_node_prefix(completed)
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
    call = await _sent_without_the_node_prefix(
        CompletedDownload(target_titles=(), filename="Keroro 062.avi", node_id=_NODE_ID)
    )
    assert call["body"] == "**Targets**\nunknown\n\n**File**\n`Keroro 062.avi`"


@pytest.mark.asyncio
async def test_a_first_useful_source_names_itself_its_targets_and_its_file() -> None:
    call = await _sent_without_the_node_prefix(_source_alert("AnimuseeFMR", absent_for=None))
    assert (call["title"], call["body"]) == (
        "📥 Source useful for the first time",
        "**Source**\n`AnimuseeFMR` 1f2e3d4c…, useful for the first time\n\n"
        "**Targets**\n062A - Les demoiselles cambrioleuses\n\n"
        "**File**\n`Keroro 062.avi`",
    )


@pytest.mark.asyncio
async def test_a_reappeared_source_says_how_long_it_was_absent() -> None:
    call = await _sent_without_the_node_prefix(
        _source_alert("AnimuseeFMR", absent_for=timedelta(hours=26))
    )
    assert (call["title"], call["body"]) == (
        "🔁 Source reappeared",
        "**Source**\n`AnimuseeFMR` 1f2e3d4c…, reappeared after 26 h\n\n"
        "**Targets**\n062A - Les demoiselles cambrioleuses\n\n"
        "**File**\n`Keroro 062.avi`",
    )


@pytest.mark.asyncio
async def test_a_source_without_a_name_or_a_target_names_its_hash_and_its_file() -> None:
    call = await _sent_without_the_node_prefix(
        _source_alert(None, absent_for=None, target_titles=())
    )
    assert call["body"] == (
        "**Source**\n1f2e3d4c…, useful for the first time\n\n**File**\n`Keroro 062.avi`"
    )


@pytest.mark.asyncio
async def test_a_backtick_in_a_source_name_cannot_close_its_code_span() -> None:
    alert = _source_alert(
        "a`@everyone`b",
        absent_for=timedelta(seconds=43_200.000001),
        target_titles=(),
        filename="x.avi",
    )
    body = (await _sent_without_the_node_prefix(alert))["body"]
    assert isinstance(body, str)
    assert body.startswith(
        "**Source**\n`a'@everyone'b` 1f2e3d4c…, reappeared after 12 h\n".replace("@", "@\u200b")
    )


@pytest.mark.asyncio
async def test_a_send_its_service_does_not_take_is_refused_with_apprise_s_answer() -> None:
    notifier, _ = _notifier(apprise.AppriseResultStatus.FAILURE)

    with pytest.raises(NotificationRefusedError, match=r"^the service refused it \(FAILURE\)$"):
        await notifier.notify(_DISCORD, notification=_LINE)


@pytest.mark.asyncio
async def test_a_real_apprise_whose_service_refuses_the_send_raises_a_refusal() -> None:
    with socket.socket() as probe:  # once closed, nothing listens on its port
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    notifier = AppriseNotifier(
        ((f"json://127.0.0.1:{port}/", Audience.COMMUNITY, False),),
        apprise_factory=apprise.Apprise,
    )
    [service] = notifier.services()

    with pytest.raises(NotificationRefusedError, match=r"^the service refused it \(FAILURE\)$"):
        await notifier.notify(service, notification=_LINE)


@pytest.mark.asyncio
async def test_a_url_a_real_apprise_cannot_load_is_refused_at_each_send() -> None:
    # A Discord URL needs a webhook's id and token: apprise loads no service from this one.
    notifier = AppriseNotifier(
        (("discord://x", Audience.COMMUNITY, False),), apprise_factory=apprise.Apprise
    )
    [service] = notifier.services()

    for _ in range(2):
        with pytest.raises(NotificationRefusedError, match=r"^apprise could not load its URL$"):
            await notifier.notify(service, notification=_LINE)
