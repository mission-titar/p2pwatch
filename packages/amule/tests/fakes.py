from p2pwatch_amule.ports.driven.account_manager import AccountManager


class FakeAccountManager(AccountManager):
    """Records the uid and gid of each account it is asked for."""

    def __init__(self) -> None:
        self.accounts: list[tuple[int, int]] = []

    def find_or_create_amule_account(self, uid: int, gid: int) -> None:
        self.accounts.append((uid, gid))
