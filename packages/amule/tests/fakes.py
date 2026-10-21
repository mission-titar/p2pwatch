from p2pwatch_amule.ports.driven.account_manager import AccountManager
from p2pwatch_amule.ports.driven.admin_password_setter import AdminPasswordSetter
from p2pwatch_amule.ports.driven.amule_conf import AmuleConfReader, AmuleConfWriter
from p2pwatch_amule.ports.driven.amuled_directory_preparer import AmuledDirectoryPreparer


class FakeAccountManager(AccountManager):
    """Records the uid and gid of each account it is asked for."""

    def __init__(self) -> None:
        self.accounts: list[tuple[int, int]] = []

    def find_or_create_amule_account(self, uid: int, gid: int) -> None:
        self.accounts.append((uid, gid))


class FakeAmuledDirectoryPreparer(AmuledDirectoryPreparer):
    """Records the uid and gid of each preparation it is asked for."""

    def __init__(self) -> None:
        self.owners: list[tuple[int, int]] = []

    def prepare_amuled_directories(self, uid: int, gid: int) -> None:
        self.owners.append((uid, gid))


class FakeAmuleConf(AmuleConfReader, AmuleConfWriter):
    """amule.conf held as text, ``None`` when absent; records the owner of each write."""

    def __init__(self) -> None:
        self.conf: str | None = None
        self.owners: list[tuple[int, int]] = []

    def read_amule_conf(self) -> str | None:
        return self.conf

    def write_amule_conf(self, conf: str, uid: int, gid: int) -> None:
        self.conf = conf
        self.owners.append((uid, gid))


class FakeAdminPasswordSetter(AdminPasswordSetter):
    """Records each password set, with the uid and gid it is set as."""

    def __init__(self) -> None:
        self.passwords: list[tuple[str, int, int]] = []

    def set_admin_password(self, api_password: str, uid: int, gid: int) -> None:
        self.passwords.append((api_password, uid, gid))
