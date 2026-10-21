from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Any, Literal, Self
from urllib.request import ProxyHandler, build_opener

from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant
from p2pwatch_amule.domain.settings_error import SettingsError
from p2pwatch_amule.ports.driven.account_manager import AccountManager
from p2pwatch_amule.ports.driven.admin_password_setter import AdminPasswordSetter
from p2pwatch_amule.ports.driven.amule_conf import AmuleConfReader, AmuleConfWriter
from p2pwatch_amule.ports.driven.amuled_directory_preparer import AmuledDirectoryPreparer
from p2pwatch_amule.ports.driven.forwarded_port_reader import ForwardedPortReader
from p2pwatch_amule.ports.driven.logger import Logger
from p2pwatch_amule.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.ports.driven.service_supervisor import ServiceSupervisor
from p2pwatch_amule.ports.driving.container_booter import ContainerBooter


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


@dataclass(frozen=True)
class LoggedLine:
    level: Literal["info", "warning", "error"]
    message: str


class FakeLogger(Logger):
    """Keeps each line, its arguments formatted in as ``logging`` does."""

    def __init__(self) -> None:
        self.lines: list[LoggedLine] = []

    def info(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("info", message % args))

    def warning(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("warning", message % args))

    def error(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("error", message % args))


class FakeMonotonicClock(MonotonicClock):
    """Its ``sleep`` records the duration and advances ``now`` at once, then calls ``on_sleep``."""

    def __init__(self) -> None:
        self.instant = MonotonicInstant(0)
        self.sleeps: list[timedelta] = []
        self.on_sleep: Callable[[], None] = lambda: None

    def now(self) -> MonotonicInstant:
        return self.instant

    def sleep(self, duration: timedelta) -> None:
        self.sleeps.append(duration)
        self.instant += duration
        self.on_sleep()


class FakeServiceSupervisor(ServiceSupervisor):
    """Records each action it is asked for, in order."""

    def __init__(self) -> None:
        self.actions: list[str] = []

    def enable_port_sync(self) -> None:
        self.actions.append("enable port-sync")

    def disable_port_sync(self) -> None:
        self.actions.append("disable port-sync")


class FakeContainerBooter(ContainerBooter):
    """Records each environment it boots in, or raises a set error."""

    def __init__(self) -> None:
        self.error: SettingsError | None = None
        self.envs: list[Mapping[str, str]] = []

    def boot_container(self, env: Mapping[str, str]) -> None:
        self.envs.append(env)
        if self.error is not None:
            raise self.error


class FakeForwardedPortReader(ForwardedPortReader):
    """Returns ``forwarded_port``, after calling ``on_read``."""

    def __init__(self) -> None:
        self.forwarded_port: int | None = 51820
        self.on_read: Callable[[], None] = lambda: None

    def read_forwarded_port(self) -> int | None:
        self.on_read()
        return self.forwarded_port


class FakeGluetunControlServer:
    """gluetun's control server on a loopback port: each GET gets ``status`` and ``body``, or
    ``raw_reply``'s bytes, or no answer while ``is_holding``; records each request line."""

    def __init__(self) -> None:
        self.status = 200
        self.body = b'{"port": 51820}'
        self.raw_reply: bytes | None = None
        self.is_holding = False
        self.request_lines: list[str] = []
        self._released = Event()
        fake_server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                # requestline, not path, which http.server strips of a leading //.
                fake_server.request_lines.append(self.requestline)
                if fake_server.is_holding:
                    fake_server._released.wait()
                    return
                if fake_server.raw_reply is not None:
                    self.wfile.write(fake_server.raw_reply)
                    return
                self.send_response(fake_server.status)
                self.send_header("Content-Length", str(len(fake_server.body)))
                self.end_headers()
                self.wfile.write(fake_server.body)

            def log_message(self, format: str, *args: Any) -> None:
                """Silent: the requests are recorded instead."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address[:2]
        self.control_url = f"http://{host!s}:{port}"
        self.url_opener = build_opener(ProxyHandler({}))  # direct, whatever HTTP_PROXY says
        # Polled every 10 ms, not 0.5 s: shutdown waits for the next poll.
        self._thread = Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01})

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._released.set()
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()
