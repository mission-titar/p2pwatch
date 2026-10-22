from p2pwatch_amule.application.ports.driven.admin_password_setter import AdminPasswordSetter


class FakeAdminPasswordSetter(AdminPasswordSetter):
    """Records each password set, with the uid and gid it is set as, in ``actions``."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions

    def set_admin_password(self, api_password: str, uid: int, gid: int) -> None:
        self.actions.append(f"admin password {api_password} as {uid}:{gid}")
