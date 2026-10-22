import apprise


class FakeApprise:
    def __init__(self, asset: apprise.AppriseAsset) -> None:
        self.asset = asset
        self.added: list[tuple[str, str]] = []
        self.sent: list[dict[str, object]] = []

    def add(self, url: str, tag: str) -> bool:
        self.added.append((url, tag))
        return True

    async def async_notify(self, **kwargs: object) -> bool:
        self.sent.append(kwargs)
        return True
