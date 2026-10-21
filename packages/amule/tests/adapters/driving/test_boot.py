"""boot main: its variables refused first, then user, mount points, amule.conf, admin pass."""

import grp
import hashlib
import os
import pwd
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from p2pwatch_amule.adapters.driving import boot as entry
from p2pwatch_amule.domain.conf import reconcile_conf
from p2pwatch_amule.domain.settings_error import SettingsError

DIGEST = hashlib.md5(b"hunter2").hexdigest()
ENV = {
    "PUID": "1000",
    "PGID": "1001",
    "AMULE_EC_PASSWORD": "hunter2",
    "AMULE_API_PASSWORD": "s3cret",
}

Call = tuple[list[str], dict[str, Any]]


class Boot:
    """main's paths under tmp_path, its environment, and its commands and chowns recorded."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.home = tmp_path / "home/amule"
        self.config = self.home / ".aMule"
        self.incoming = tmp_path / "downloads/incoming"
        self.temp = tmp_path / "downloads/temp"
        self.conf = self.config / "amule.conf"
        self.port_sync_down = tmp_path / "services.d/port-sync/down"
        self.port_sync_down.parent.mkdir(parents=True)
        self.env = dict(ENV)
        self.amule_exists = False
        self.calls: list[Call] = []
        self.chowns: list[tuple[Path, int, int]] = []
        monkeypatch.setattr(grp, "getgrnam", self._lookup)
        monkeypatch.setattr(pwd, "getpwnam", self._lookup)
        monkeypatch.setattr(subprocess, "run", self._run)
        monkeypatch.setattr(os, "chown", self._chown)

    def main(self) -> None:
        entry.main(
            self.env,
            home_directory=self.home,
            config_directory=self.config,
            incoming_directory=self.incoming,
            temporary_directory=self.temp,
            amule_conf_path=self.conf,
            port_sync_down_file=self.port_sync_down,
        )

    def _lookup(self, name: str) -> object:
        assert name == "amule"
        if not self.amule_exists:
            raise KeyError(name)
        return object()

    def _run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    def _chown(self, path: Path, uid: int, gid: int) -> None:
        self.chowns.append((path, uid, gid))

    def set_admin_pass(self) -> Call:
        argv = ["amuleapi", f"--config-dir={self.config}", "--set-admin-pass=s3cret"]
        kwargs = {
            "user": 1000,
            "group": 1001,
            "extra_groups": [],
            "env": {**self.env, "HOME": str(self.home)},
            "check": True,
        }
        return argv, kwargs


@pytest.fixture
def boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Boot:
    return Boot(tmp_path, monkeypatch)


def test_first_boot_creates_the_user_and_writes_the_minimal_conf(boot: Boot) -> None:
    boot.main()
    useradd = ["useradd", "-o", "-u", "1000", "-g", "1001", "-M", "-d", str(boot.home)]
    assert boot.calls == [
        (["groupadd", "-o", "-g", "1001", "amule"], {"check": True}),
        ([*useradd, "-s", "/usr/sbin/nologin", "amule"], {"check": True}),
        boot.set_admin_pass(),
    ]
    assert boot.conf.read_text() == reconcile_conf(None, DIGEST)


def test_existing_user_and_group_are_not_recreated(boot: Boot) -> None:
    boot.amule_exists = True
    boot.main()
    assert boot.calls == [boot.set_admin_pass()]


def test_mount_points_are_created_and_owned_but_not_their_contents(boot: Boot) -> None:
    boot.main()
    owned = [boot.home, boot.config, boot.incoming, boot.temp]
    assert all(directory.is_dir() for directory in owned)
    assert boot.chowns == [(path, 1000, 1001) for path in [*owned, boot.conf]]


def test_the_conf_is_private_to_its_owner(boot: Boot) -> None:
    boot.main()
    assert stat.S_IMODE(boot.conf.stat().st_mode) == 0o600


def test_an_existing_conf_is_reconciled_not_replaced(boot: Boot) -> None:
    boot.config.mkdir(parents=True)
    boot.conf.write_text("[eMule]\nMaxUpload=42\n\n[ExternalConnect]\nECPassword=dead\n")
    boot.main()
    assert boot.conf.read_text() == reconcile_conf(
        "[eMule]\nMaxUpload=42\n\n[ExternalConnect]\nECPassword=dead\n", DIGEST
    )


def test_the_admin_password_is_the_one_set(boot: Boot) -> None:
    boot.env["AMULE_API_PASSWORD"] = "mot de passé"
    boot.main()
    assert "--set-admin-pass=mot de passé" in boot.calls[-1][0]


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"PUID": ""}, "PUID is required"),
        ({"PGID": "amule"}, "PGID must be a numeric id, got 'amule'"),
        ({"AMULE_API_PASSWORD": "s3cret\n"}, "AMULE_API_PASSWORD must not contain a control"),
        ({"PORT_SYNC": "maybe"}, "PORT_SYNC must be one of "),
        ({"PORT_SYNC": "on", "PORT_SYNC_POLL_SECONDS": "0"}, "PORT_SYNC_POLL_SECONDS must be "),
        ({"PORT_SYNC": "yes", "GLUETUN_CONTROL_URL": "gluetun"}, "GLUETUN_CONTROL_URL must be "),
    ],
)
def test_a_refused_variable_aborts_the_boot_before_any_change(
    boot: Boot, variables: dict[str, str], message: str
) -> None:
    boot.env.update(variables)
    with pytest.raises(SettingsError, match=f"^{re.escape(message)}"):
        boot.main()
    assert boot.calls == []
    assert boot.chowns == []
    assert not boot.home.exists()


def test_port_sync_off_leaves_its_other_variables_unread(boot: Boot) -> None:
    boot.env.update({"PORT_SYNC": "off", "PORT_SYNC_POLL_SECONDS": "0"})
    boot.main()
    assert boot.calls[-1] == boot.set_admin_pass()


@pytest.mark.parametrize("value", ["off", "", None])
def test_port_sync_off_or_unset_keeps_its_service_down(boot: Boot, value: str | None) -> None:
    if value is not None:
        boot.env["PORT_SYNC"] = value
    boot.main()
    assert boot.port_sync_down.is_file()


@pytest.mark.parametrize("value", ["yes", "On"])
def test_port_sync_on_lets_s6_start_its_service(boot: Boot, value: str) -> None:
    boot.port_sync_down.touch()
    boot.env["PORT_SYNC"] = value
    boot.main()
    assert not boot.port_sync_down.exists()


def test_port_sync_on_without_a_down_file_boots(boot: Boot) -> None:
    boot.env["PORT_SYNC"] = "on"
    boot.main()
    assert not boot.port_sync_down.exists()
