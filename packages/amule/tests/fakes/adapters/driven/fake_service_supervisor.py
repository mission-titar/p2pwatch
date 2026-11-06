from p2pwatch_amule.application.ports.driven.service_supervisor import ServiceSupervisor


class FakeServiceSupervisor(ServiceSupervisor):
    """Records each action it is asked for in ``actions``."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions

    def enable_port_sync(self) -> None:
        self.actions.append("enable port-sync")

    def disable_port_sync(self) -> None:
        self.actions.append("disable port-sync")
