from typing import Protocol

from p2pwatch_amule.application.ports.driven.service_supervisor import ServiceSupervisor


class StopCallback(Protocol):
    def __call__(self) -> None: ...


class FakeServiceSupervisor(ServiceSupervisor):
    """Records each action it is asked for in ``actions``; a stop calls ``on_stop_amuled``, then
    returns ``is_amuled_stopped``."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions
        self.is_amuled_stopped = True
        self.on_stop_amuled: StopCallback = lambda: None

    def enable_port_sync(self) -> None:
        self.actions.append("enable port-sync")

    def disable_port_sync(self) -> None:
        self.actions.append("disable port-sync")

    def stop_amuled(self) -> bool:
        self.actions.append("stop amuled")
        self.on_stop_amuled()
        return self.is_amuled_stopped

    def start_amuled(self) -> None:
        self.actions.append("start amuled")
