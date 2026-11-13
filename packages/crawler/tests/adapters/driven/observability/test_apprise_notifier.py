"""Apprise notifier: a service per URL, named by its scheme and audience, an apprise object per
node and service holding its URL alone, the node_id in the title of a prefixed service, each
kind's Markdown and notify type, mentions neutralised, a relayed log line sent untitled."""

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
from p2pwatch.domain.observability.notifier_outcomes import (
    NotificationRefused,
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
_SUCCESS = apprise.AppriseResultStatus.SUCCESS
_PREFIXED, _OPERATIONS, _BARE = (
    NotificationService(scheme="discord", audience=Audience.COMMUNITY),
    NotificationService(scheme="discord", audience=Audience.OPERATIONS),
    NotificationService(scheme="discord", audience=Audience.COMMUNITY, ordinal=2),
)


def _notifier(
    *statuses: apprise.AppriseResultStatus,
) -> tuple[AppriseNotifier, list[FakeApprise]]:
    """The notifier and every apprise object it builds, in order, the nth answering the nth of
    ``statuses``, a success past them."""
    targets = (
        ("discord://x", Audience.COMMUNITY, True),
        ("discord://y", Audience.OPERATIONS, True),
        ("discord://z", Audience.COMMUNITY, False),
    )
    built: list[FakeApprise] = []

    def factory(*, asset: apprise.AppriseAsset) -> FakeApprise:
        status = statuses[len(built)] if len(built) < len(statuses) else _SUCCESS
        built.append(FakeApprise(asset=asset, status=status))
        return built[-1]

    return AppriseNotifier(targets, apprise_factory=factory), built


async def _sent_to_the_bare_service(notification: Notification) -> dict[str, object]:
    """What the bare service, whose title has no node prefix, is sent for ``notification``."""
    notifier, built = _notifier()
    await notifier.notify(_BARE, notification=notification)
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


def test_each_url_is_a_service_named_by_its_scheme_and_its_audience_never_its_url() -> None:
    notifier, _ = _notifier()
    assert notifier.services() == (_PREFIXED, _OPERATIONS, _BARE)
    odd = AppriseNotifier(
        (("JSON://host/", Audience.OPERATIONS, True), ("token-123", Audience.OPERATIONS, True)),
        apprise_factory=apprise.Apprise,
    )
    assert [str(service) for service in odd.services()] == ["json operations", "unknown operations"]


@pytest.mark.asyncio
async def test_each_service_gets_an_apprise_object_holding_its_url_alone() -> None:
    notifier, built = _notifier()
    assert built == []  # nothing built before a notification names its node
    for service in (_PREFIXED, _OPERATIONS, _BARE):
        await notifier.notify(service, notification=_LINE)
    assert [one.added for one in built] == [
        [("discord://x", {})],
        [("discord://y", {})],
        [("discord://z", {})],
    ]
    assert [len(one.sent) for one in built] == [1, 1, 1]


@pytest.mark.asyncio
async def test_each_apprise_object_names_the_node_and_sends_no_image() -> None:
    notifier, built = _notifier()
    await notifier.notify(_PREFIXED, notification=_LINE)
    await notifier.notify(_BARE, notification=_LINE)
    for asset in (one.asset for one in built):
        assert asset.app_id == "p2pwatch - titar-node-1"
        assert asset.app_url == "https://github.com/mission-titar/p2pwatch"
        assert asset.image_url(apprise.NotifyType.INFO) is None
        assert asset.image_url(apprise.NotifyType.INFO, logo=True) is None


@pytest.mark.asyncio
async def test_a_node_keeps_its_apprise_object_and_another_node_gets_its_own() -> None:
    notifier, built = _notifier()
    await notifier.notify(_PREFIXED, notification=_LINE)
    await notifier.notify(_PREFIXED, notification=_LINE)
    await notifier.notify(
        _PREFIXED,
        notification=CompletedDownload(
            target_titles=(_062A,), filename="Keroro 062.avi", node_id=NodeId("titar-node-2")
        ),
    )
    assert [one.asset.app_id for one in built] == [
        "p2pwatch - titar-node-1",
        "p2pwatch - titar-node-2",
    ]
    assert [len(one.sent) for one in built] == [2, 1]
    assert [call["title"] for call in built[1].sent] == ["[titar-node-2] ✅ Downloaded"]


@pytest.mark.asyncio
async def test_the_node_prefix_goes_into_the_title_of_a_prefixed_service_only() -> None:
    notifier, built = _notifier()
    for service in (_PREFIXED, _BARE):
        await notifier.notify(service, notification=_rise(DecisionTier.DOWNLOAD))
        await notifier.notify(service, notification=_LINE)
    prefixed, bare = built
    assert [c["title"] for c in prefixed.sent + bare.sent] == [
        "[titar-node-1] 📥 Download",
        "[titar-node-1]",
        "📥 Download",
        "",
    ]
    assert [c["body"] for c in prefixed.sent] == [c["body"] for c in bare.sent]
    assert bare.sent[1]["body"] == "online"
    assert all("tag" not in call for call in prefixed.sent + bare.sent)


@pytest.mark.asyncio
async def test_every_message_is_sent_as_markdown() -> None:
    notifier, built = _notifier()
    await notifier.notify(
        _OPERATIONS,
        notification=RelayedLogLine(message="x", severity=Severity.WARNING, node_id=_NODE_ID),
    )
    await notifier.notify(_BARE, notification=_rise(DecisionTier.NOTIFY))
    calls = [call for one in built for call in one.sent]
    assert [c["body_format"] for c in calls] == [apprise.NotifyFormat.MARKDOWN] * 2


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
    await notifier.notify(_PREFIXED, notification=alert)
    await notifier.notify(
        _OPERATIONS,
        notification=RelayedLogLine(message=hostile, severity=Severity.WARNING, node_id=_NODE_ID),
    )
    for call in (call for one in built for call in one.sent):
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
        _OPERATIONS,
        notification=RelayedLogLine(message="x", severity=severity, node_id=_NODE_ID),
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
    assert (await _sent_to_the_bare_service(notification))["notify_type"] == notify_type


@pytest.mark.asyncio
async def test_a_rise_names_its_tier_its_targets_its_file_and_its_link() -> None:
    call = await _sent_to_the_bare_service(_rise(DecisionTier.DOWNLOAD))
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
    assert (await _sent_to_the_bare_service(_rise(DecisionTier.NOTIFY)))["title"] == "🔎 Notify"


@pytest.mark.asyncio
async def test_a_backtick_in_the_name_cannot_close_its_code_span() -> None:
    # Discord pings a mention outside code: a name must not escape its span.
    call = await _sent_to_the_bare_service(
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
    call = await _sent_to_the_bare_service(completed)
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
    call = await _sent_to_the_bare_service(
        CompletedDownload(target_titles=(), filename="Keroro 062.avi", node_id=_NODE_ID)
    )
    assert call["body"] == "**Targets**\nunknown\n\n**File**\n`Keroro 062.avi`"


@pytest.mark.asyncio
async def test_a_first_useful_source_names_itself_its_targets_and_its_file() -> None:
    call = await _sent_to_the_bare_service(_source_alert("AnimuseeFMR", absent_for=None))
    assert (call["title"], call["body"]) == (
        "📥 Source useful for the first time",
        "**Source**\n`AnimuseeFMR` 1f2e3d4c…, useful for the first time\n\n"
        "**Targets**\n062A - Les demoiselles cambrioleuses\n\n"
        "**File**\n`Keroro 062.avi`",
    )


@pytest.mark.asyncio
async def test_a_reappeared_source_says_how_long_it_was_absent() -> None:
    call = await _sent_to_the_bare_service(
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
    call = await _sent_to_the_bare_service(_source_alert(None, absent_for=None, target_titles=()))
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
    body = (await _sent_to_the_bare_service(alert))["body"]
    assert isinstance(body, str)
    assert body.startswith(
        "**Source**\n`a'@everyone'b` 1f2e3d4c…, reappeared after 12 h\n".replace("@", "@\u200b")
    )


class TestAppriseNotifier(NotifierContract):
    def notifier(self) -> Notifier:
        return _notifier()[0]

    def refusing_notifier(self) -> Notifier:
        return _notifier(*[apprise.AppriseResultStatus.FAILURE] * 3)[0]


def test_a_notifier_without_a_url_has_no_service() -> None:
    assert AppriseNotifier((), apprise_factory=apprise.Apprise).services() == ()


@pytest.mark.asyncio
async def test_a_success_raises_nothing() -> None:
    notifier, _ = _notifier(_SUCCESS)
    await notifier.notify(_PREFIXED, notification=_LINE)  # does not raise


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "refused",
    [
        apprise.AppriseResultStatus.FAILURE,
        apprise.AppriseResultStatus.PARTIAL,
        apprise.AppriseResultStatus.TIMEOUT,
        apprise.AppriseResultStatus.NOMATCH,  # its URL loaded no service
    ],
)
async def test_any_answer_but_a_success_raises_notification_refused(
    refused: apprise.AppriseResultStatus,
) -> None:
    notifier, _ = _notifier(refused)
    with pytest.raises(NotificationRefused, match=rf"^refused \({refused.name}\)$"):
        await notifier.notify(_PREFIXED, notification=_LINE)


@pytest.mark.asyncio
async def test_a_real_apprise_whose_url_it_cannot_load_refuses_each_send() -> None:
    notifier = AppriseNotifier(
        (("nosuchscheme://x/y", Audience.OPERATIONS, True),), apprise_factory=apprise.Apprise
    )
    [service] = notifier.services()
    with pytest.raises(NotificationRefused, match=r"^refused \(NOMATCH\)$"):
        await notifier.notify(service, notification=_LINE)


@pytest.mark.asyncio
async def test_a_real_apprise_whose_service_refuses_its_connection_raises_a_refusal() -> None:
    with socket.socket() as probe:  # a port no one listens on once it is closed
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    notifier = AppriseNotifier(
        ((f"json://127.0.0.1:{port}/", Audience.COMMUNITY, False),),
        apprise_factory=apprise.Apprise,
    )
    [service] = notifier.services()
    with pytest.raises(NotificationRefused):
        await notifier.notify(service, notification=_LINE)
