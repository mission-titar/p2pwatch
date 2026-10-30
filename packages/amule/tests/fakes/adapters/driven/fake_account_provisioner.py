from p2pwatch_amule.application.ports.driven.account_provisioner import AccountProvisioner
from p2pwatch_amule.domain.identifiers import Gid, Uid


class FakeAccountProvisioner(AccountProvisioner):
    """Records each account it is asked for in ``actions``."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions

    def find_or_create_amule_account(self, uid: Uid, *, gid: Gid) -> None:
        self.actions.append(f"account {uid}:{gid}")
