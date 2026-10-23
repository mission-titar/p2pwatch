"""Apprise notifier: routes a notification per AUDIENCE via apprise tags (E-D7).

ADAPTER ring (implements ``Notifier``). On a ``node_id``'s first notification:
``add(url, tag=audience)`` for each target, into one of two apprise groups: prefixed or bare
(``node_prefix``). ``notify`` sends the title PREFIXED with the ``node_id`` (distributed network)
to the first group and as is to the second, since apprise sends one message to every URL of a
tag. Every message is markdown (a Discord embed) with every ``@`` neutralised, and both groups
share an asset naming the node (spec discord-embed-notifications §4). No URL → natural no-op
(apprise with no service returns ``None``). ``apprise_factory`` builds a group: ``apprise.Apprise``
from the composition. The timeout/error absorption live in the dispatch step (E-D13).

DECISION (audit 2026-06-23 / security-network#2): the apprise egress (Slack, Discord, SMTP,
etc. webhooks) traverses the crawler's HOST network, not the VPN. The packaging spec accepts this
tradeoff: the P2P kill-switch stays effective (eD2k blocked outside the VPN, anonymity preserved);
only the notification IP↔webhook CORRELATION remains (an operator who notifies on Slack exposes
their host's IP to Slack, not their P2P traffic). This is a DELIBERATE choice, not a flaw.

No apprise stubs → targeted ``# type: ignore`` (mypy override, Task 9)."""

from collections.abc import Callable, Sequence
from typing import assert_never

import apprise

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification import (
    Notification,
    RelayedLogLine,
    TextNotification,
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
    Severity.ERROR: apprise.NotifyType.FAILURE,
}


# apprise extracts "@word", "<@id>" and "<@&id>" from markdown into pings: a zero-width space breaks
# every one of them, and p2pwatch never mentions anyone.
_NO_MENTION = "@\u200b"


class AppriseNotifier(Notifier):
    """``Notifier`` adapter: one apprise tag per audience, in a prefixed group and a bare one."""

    def __init__(self, targets: AppriseTargets, *, apprise_factory: Callable[..., object]) -> None:
        self._targets = targets
        self._apprise_factory = apprise_factory
        self._groups_by_node_id: dict[str, tuple[object, object]] = {}

    def _groups(self, node_id: str) -> tuple[object, object]:
        """The node's prefixed and bare groups, built on its first notification."""
        # Per node: apprise hands the asset, its username, to each URL when it is added.
        if node_id in self._groups_by_node_id:
            return self._groups_by_node_id[node_id]
        # No image: a Discord webhook keeps its own avatar.
        asset = apprise.AppriseAsset(
            app_id=f"p2pwatch - {node_id}",
            app_url="https://github.com/mission-titar/p2pwatch",
            image_url_mask="",
            image_url_logo="",
        )
        # Typed ``object`` on purpose: the adapter does not depend on apprise's (untyped)
        # surface; ``.add``/``.async_notify`` carry a ``# type: ignore[attr-defined]``.
        prefixed_group: object = self._apprise_factory(asset=asset)
        bare_group: object = self._apprise_factory(asset=asset)
        for url, audience, node_prefix in self._targets:
            group = prefixed_group if node_prefix else bare_group
            group.add(url, tag=audience.value)  # type: ignore[attr-defined]
        self._groups_by_node_id[node_id] = (prefixed_group, bare_group)
        return prefixed_group, bare_group

    async def notify(self, audience: Audience, notification: Notification) -> None:
        match notification:
            case TextNotification():
                title, body = notification.title, notification.body
            case RelayedLogLine():  # untitled: the log line is the whole message
                title, body = "", notification.message
            case _:  # pragma: no cover
                assert_never(notification)
        node_id = notification.node_id
        prefixed_group, bare_group = self._groups(node_id)
        prefixed = f"[{node_id}] {title}".rstrip()
        for group, heading in ((prefixed_group, prefixed), (bare_group, title)):
            await group.async_notify(  # type: ignore[attr-defined]
                title=heading.replace("@", _NO_MENTION),
                body=body.replace("@", _NO_MENTION),
                body_format=apprise.NotifyFormat.MARKDOWN,
                notify_type=_NOTIFY_TYPES[notification.severity],
                tag=audience.value,
            )
