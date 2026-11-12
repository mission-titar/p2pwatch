"""Apprise notifier: one service per target URL, its audience the config's (E-D7).

ADAPTER ring (implements ``Notifier``). Each target is a service, named by its URL's scheme and
its audience, never by its URL, which carries a webhook's token. On a ``node_id``'s first
notification to a service, one apprise object holds that service's URL alone, so each send has
its own answer. A ``node_prefix`` service's title is PREFIXED with the ``node_id`` (distributed
network). A community kind's title, Markdown body and notify type are written here; a relayed log
line is sent untitled, its severity mapped. Every message is markdown (a Discord embed) with
every ``@`` neutralised, and each object's asset names the node (spec
discord-embed-notifications §4). Any answer but a success, a URL apprise could not load
(``NOMATCH``) included, raises ``NotificationRefused``. ``apprise_factory`` builds an object:
``apprise.Apprise`` from the composition. The timeout lives in the dispatch step (E-D13).

DECISION (audit 2026-06-23 / security-network#2): the apprise egress (Slack, Discord, SMTP,
etc. webhooks) traverses the crawler's HOST network, not the VPN. The packaging spec accepts this
tradeoff: the P2P kill-switch stays effective (eD2k blocked outside the VPN, anonymity preserved);
only the notification IP↔webhook CORRELATION remains (an operator who notifies on Slack exposes
their host's IP to Slack, not their P2P traffic). This is a DELIBERATE choice, not a flaw."""

from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol, assert_never

import apprise

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.ed2k_link import build_ed2k_link
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.matching.decision_tier import DecisionTier
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

# (url, audience, node_prefix), from the config's ``observability.notifications``.
AppriseTargets = Sequence[tuple[str, Audience, bool]]

_NOTIFY_TYPES: dict[Severity, object] = {
    Severity.DEBUG: apprise.NotifyType.INFO,
    Severity.INFO: apprise.NotifyType.INFO,
    Severity.SUCCESS: apprise.NotifyType.SUCCESS,
    Severity.WARNING: apprise.NotifyType.WARNING,
}


_RISE_TITLES = {DecisionTier.DOWNLOAD: "📥 Download", DecisionTier.NOTIFY: "🔎 Notify"}
_SOURCE_ALERT_TITLES = {
    SourceAlertKind.FIRST_USEFUL: "📥 Source useful for the first time",
    SourceAlertKind.REAPPEARED: "🔁 Source reappeared",
}


def _targets_section(target_titles: tuple[TargetTitle, ...]) -> str:
    return "**Targets**\n" + (
        "\n".join(f"{t.target_id} - {t.title}" for t in target_titles) or "unknown"
    )


def _code_name(filename: str) -> str:
    # A backtick would close the span and let the rest of the name read as markup.
    return "`" + filename.replace("`", "'") + "`"


def _rise_body(rise: TierRise) -> str:
    match rise.file.network:
        case Network.ED2K:
            link = build_ed2k_link(
                rise.filename, size_bytes=rise.size_bytes, native_id=rise.file.native_id
            )
        case _:  # pragma: no cover
            assert_never(rise.file.network)
    return (
        _targets_section(rise.target_titles)
        + f"\n\n**File**\n{rise.size_bytes / 2**20:.1f} MiB - {_code_name(rise.filename)}"
        + f"\n\n**ed2k**\n`{link}`"
    )


def _source_state(absent_for: timedelta | None) -> str:
    """The phrase the source alert's log line also says."""
    if absent_for is None:
        return "useful for the first time"
    return f"reappeared after {absent_for / timedelta(hours=1):.0f} h"


def _source_alert_body(alert: SourceAlert) -> str:
    short = f"{alert.source.native_id[:8]}…"  # as the webui shortens a hash
    named = f"{_code_name(alert.source_name)} " if alert.source_name else ""
    sections = [f"**Source**\n{named}{short}, {_source_state(alert.absent_for)}"]
    if alert.target_titles:
        sections.append(_targets_section(alert.target_titles))
    sections.append(f"**File**\n{_code_name(alert.filename)}")
    return "\n\n".join(sections)


def _completed_download_body(completed: CompletedDownload) -> str:
    return _targets_section(completed.target_titles) + (
        f"\n\n**File**\n{_code_name(completed.filename)}"
    )


def _message(notification: Notification) -> tuple[str, str, object]:
    """The notification's title, Markdown body and apprise notify type."""
    match notification:
        case TierRise():
            title, body = _RISE_TITLES[notification.tier], _rise_body(notification)
            return title, body, apprise.NotifyType.INFO
        case SourceAlert():
            title = _SOURCE_ALERT_TITLES[notification.kind]
            return title, _source_alert_body(notification), apprise.NotifyType.INFO
        case CompletedDownload():
            body = _completed_download_body(notification)
            return "✅ Downloaded", body, apprise.NotifyType.SUCCESS
        case RelayedLogLine():  # untitled: the log line is the whole message
            return "", notification.message, _NOTIFY_TYPES[notification.severity]
        case _:  # pragma: no cover
            assert_never(notification)


# apprise extracts "@word", "<@id>" and "<@&id>" from markdown into pings: a zero-width space breaks
# every one of them, and p2pwatch never mentions anyone.
_NO_MENTION = "@\u200b"


class AppriseFactory(Protocol):
    def __call__(self, *, asset: apprise.AppriseAsset) -> apprise.Apprise: ...


def _scheme(url: str) -> str:
    """The URL's scheme, ``unknown`` without one: the rest of a URL may be a token."""
    scheme, separator, _ = url.partition("://")
    return scheme.lower() if separator else "unknown"


def _services(targets: AppriseTargets) -> tuple[NotificationService, ...]:
    """A service per target, a second of the same scheme and audience told apart by its ordinal."""
    services: list[NotificationService] = []
    for url, audience, _ in targets:
        scheme = _scheme(url)
        alike = sum((s.scheme, s.audience) == (scheme, audience) for s in services)
        services.append(NotificationService(scheme=scheme, audience=audience, ordinal=alike + 1))
    return tuple(services)


class AppriseNotifier(Notifier):
    """``Notifier`` adapter: a service per target URL, sent to through an apprise object of its
    own per node."""

    def __init__(self, targets: AppriseTargets, *, apprise_factory: AppriseFactory) -> None:
        self._targets_by_service = {
            service: (url, node_prefix)
            for service, (url, _, node_prefix) in zip(_services(targets), targets, strict=True)
        }
        self._apprise_factory = apprise_factory
        self._apprise_by_node_and_service: dict[
            tuple[NodeId, NotificationService], apprise.Apprise
        ] = {}

    def services(self) -> tuple[NotificationService, ...]:
        return tuple(self._targets_by_service)

    def _apprise(self, service: NotificationService, *, node_id: NodeId) -> apprise.Apprise:
        """The object sending the node's notifications to ``service``, built on the first one."""
        # Per node: apprise hands the asset, its username, to the URL when it is added.
        if (node_id, service) in self._apprise_by_node_and_service:
            return self._apprise_by_node_and_service[node_id, service]
        # No image: a Discord webhook keeps its own avatar.
        asset = apprise.AppriseAsset(
            app_id=f"p2pwatch - {node_id}",
            app_url="https://github.com/mission-titar/p2pwatch",
            image_url_mask="",
            image_url_logo="",
        )
        sender = self._apprise_factory(asset=asset)
        sender.add(self._targets_by_service[service][0])
        self._apprise_by_node_and_service[node_id, service] = sender
        return sender

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        title, body, notify_type = _message(notification)
        node_id = notification.node_id
        _, node_prefix = self._targets_by_service[service]
        heading = f"[{node_id}] {title}".rstrip() if node_prefix else title
        result = await self._apprise(service, node_id=node_id).async_notify(
            title=heading.replace("@", _NO_MENTION),
            body=body.replace("@", _NO_MENTION),
            body_format=apprise.NotifyFormat.MARKDOWN,
            notify_type=notify_type,
        )
        if result.status is not apprise.AppriseResultStatus.SUCCESS:
            raise NotificationRefused(f"refused ({result.status.name})")
