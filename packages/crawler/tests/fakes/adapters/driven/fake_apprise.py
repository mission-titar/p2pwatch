import apprise


class FakeApprise(apprise.Apprise):
    """An ``apprise.Apprise`` that records the URLs added and the notifications, sends none, and
    answers each with ``status``."""

    def __init__(
        self,
        *,
        asset: apprise.AppriseAsset,
        status: apprise.AppriseResultStatus = apprise.AppriseResultStatus.SUCCESS,
    ) -> None:
        super().__init__(asset=asset)
        self.added: list[tuple[object, object]] = []
        self.sent: list[dict[str, object]] = []
        self._status = status

    def add(self, *args: object, **kwargs: object) -> bool:
        """Records ``add(url, tag=...)``, the notifier's call."""
        self.added.append((args[0], kwargs["tag"]))
        return True

    async def async_notify(self, *args: object, **kwargs: object) -> apprise.AppriseResult:
        self.sent.append(kwargs)
        return apprise.AppriseResult(status=self._status)
