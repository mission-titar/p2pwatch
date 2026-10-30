"""e2e smoke of the ASSEMBLED docker compose stack, without VPN.

Dedicated run: ( cd packages/crawler && uv run pytest -m compose_integration --no-cov )
Docker + docker compose v2 required. Brings up the TWO services of tests/smoke/compose.yaml,
the core `p2pwatch` and the aMule container `ed2k`, and asserts the WIRING, NO real download
(amuled has neither an eD2k server nor a VPN):
  1. `docker compose build` succeeds (both images build).
  2. both containers run, `ed2k` turns `healthy`, the core reaches amuleapi at `ed2k:4711` and
     shows its first reading of `amuled` on the dashboard, and writes data/ as PUID.
  3. deploy/'s layout renders with `docker compose config`, in both variants.
  4. port-sync stays down with PORT_SYNC unset; started against a stand-in for gluetun, it
     restarts amuled on the forwarded port only when that port moved.
Tear-down: `docker compose down -v` plus the throwaway state directory, in a finally.
The suite refuses to run as root: a PUID of 0 would make the ownership check pass on a root file.

The suite needs an engine whose bind mounts are REAL KERNEL MOUNTS. Under Docker Desktop on
Linux the state lives in the Desktop VM's mediated mount, which does not keep SQLite's `-shm`
coherent between processes: the crawler stamps a completion its own connection sees and no other
process ever does, so `test_a_file_amuled_shares_is_recorded_completed` fails there and only
there. `DOCKER_CONTEXT` and `DOCKER_HOST` are forwarded to the CLI (`_docker_env`) precisely so
the run can be pointed at another engine.

Mechanics established EMPIRICALLY (compose v5, Docker 29):
  * The compose file's relative paths are resolved against the project-directory. We PIN it
    explicitly to `_REPOSITORY_ROOT` via `--project-directory` (cf. `_run`): `./tests/smoke/...` and
    `context: .` resolve deterministically, without depending on the default (cwd vs the `-f`
    file's directory). The `subprocess.run` calls also run `cwd=_REPOSITORY_ROOT`.
  * State lives in BIND MOUNTS under `SMOKE_STATE`, like the real stacks: named volumes are
    gone. The test creates the three subdirectories as the invoking user and passes its own
    uid/gid as PUID/PGID, so the smoke exercises the real ownership path: the aMule container's
    root PID 1 chowns its mount points, then drops to the `amule` user, and the core runs as
    `user: PUID:PGID` from the start. A regression on that path shows up as
    `unable to open database file`.
  * The aMule image hard-requires PUID, PGID, AMULE_EC_PASSWORD and AMULE_API_PASSWORD: without
    them its boot step exits 1 and the container dies. They are supplied on every compose call,
    since the file is re-parsed each time (and each has a `:?` guard).
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping
from functools import partial
from pathlib import Path
from typing import Any, Protocol

import pytest

pytestmark = pytest.mark.compose_integration

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SMOKE = _REPOSITORY_ROOT / "tests/smoke/compose.yaml"

_CORE = "p2pwatch"
_AMULE = "ed2k"

# In CI, the build step pre-builds the image and passes IMAGE_TAG; the smoke then consumes it
# WITHOUT a rebuild. Locally (IMAGE_TAG absent) we rebuild via compose, as before.
_IMAGE_TAG = os.environ.get("IMAGE_TAG")
_USES_PREBUILT = _IMAGE_TAG is not None
_BUILD_FLAGS: tuple[str, ...] = () if _USES_PREBUILT else ("--build",)

_DEPLOY = _REPOSITORY_ROOT / "deploy"
# The include line an operator edits to switch variant.
_DIRECT_INCLUDE = "ed2k/direct.compose.yml"
_VARIANTS = ("direct", "vpn")

# Isolated project (unique prefix per run) so we NEVER touch a real stack on the host.
_PROJECT = f"emule_smoke_{uuid.uuid4().hex[:8]}"

# Throwaway bind-mount root, named after the project so two runs never share it. Computed, not
# created, at import time: this module is collected by every gate run, and only the fixture
# below (which runs when the suite is actually selected) touches the filesystem.
_STATE_DIRECTORY = Path(tempfile.gettempdir()) / _PROJECT
_STATE_SUBDIRECTORIES = ("amule", "data", "downloads")

_EC_PASSWORD = "smoke-ec-password"
_API_PASSWORD = "smoke-api-password"

# Everything the smoke stack interpolates. PUID/PGID are OURS on purpose: the bind mounts must
# stay readable from the host, which is the whole reason named volumes were dropped.
_SMOKE_ENV = {
    "PUID": str(os.getuid()),
    "PGID": str(os.getgid()),
    "AMULE_EC_PASSWORD": _EC_PASSWORD,
    "AMULE_API_PASSWORD": _API_PASSWORD,
    "SMOKE_STATE": str(_STATE_DIRECTORY),
}

# The `.env` the render test writes beside its copy of compose.yml, and ONLY there. Values no
# default could produce, so a PUID that renders proves it came from this file.
_RENDER_DOTENV = {
    "PUID": "4242",
    "PGID": "4343",
    "AMULE_EC_PASSWORD": "render-ec-password",
    "AMULE_API_PASSWORD": "x",
    "WIREGUARD_PRIVATE_KEY": "x",
    "VPN_PORT_FORWARDING": "yes",
}

# The ONLY two variables of the caller's environment the docker CLI is allowed to see. They pick
# WHICH daemon answers, they change nothing about what the suite does, and without them the suite
# is unpointable at anything but the machine's default context - which on a host running Docker
# Desktop is the Desktop VM, whose mediated bind mounts break this suite (see the module docstring).
# CI sets neither, so CI behaviour is unchanged. Everything else stays stripped: the sanitised
# environment is what keeps the smoke reproducible.
_DAEMON_SELECTORS = ("DOCKER_CONTEXT", "DOCKER_HOST")


def _docker_env(caller_env: Mapping[str, str], *extra: Mapping[str, str]) -> dict[str, str]:
    """The environment handed to a `docker` subprocess: the caller's PATH, the stubs, the
    caller's daemon selectors."""
    env = {"PATH": caller_env.get("PATH", "/usr/bin:/bin")}
    for mapping in extra:
        env.update(mapping)
    for name in _DAEMON_SELECTORS:
        selector = caller_env.get(name)
        if selector is not None:
            env[name] = selector
    return env


def _run(
    *args: str,
    files: tuple[Path, ...],
    timeout: float,
    caller_env: Mapping[str, str] = os.environ,
) -> subprocess.CompletedProcess[str]:
    """Run `docker compose -p <project> -f ... <args>` from the repo root (cwd)."""
    file_flags: list[str] = []
    for path in files:
        file_flags += ["-f", str(path)]
    command = [
        "docker",
        "compose",
        "-p",
        _PROJECT,
        "--project-directory",
        str(_REPOSITORY_ROOT),
        *file_flags,
        *args,
    ]
    return subprocess.run(
        command,
        cwd=_REPOSITORY_ROOT,
        env=_docker_env(
            caller_env, _SMOKE_ENV, {"IMAGE_TAG": _IMAGE_TAG} if _IMAGE_TAG is not None else {}
        ),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _down(files: tuple[Path, ...]) -> None:
    """Idempotent tear-down: removes the project's containers + volumes + orphans."""
    _run("down", "-v", "--remove-orphans", files=files, timeout=180)


def _ps_field(service: str, field: str, files: tuple[Path, ...]) -> str:
    """One field of the service's `ps -a --format json` entry (one JSON object per line)."""
    compose_run = _run("ps", "-a", "--format", "json", service, files=files, timeout=60)
    for line in compose_run.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        container = json.loads(line)
        if container.get("Service") == service:
            return str(container.get(field))
    return f"<absent from `ps`: {compose_run.stdout!r}>"


def _exec(service: str, *command: str, files: tuple[Path, ...]) -> str:
    """Run a command in `service`; on failure return the error AS the observed value.

    Tolerant on purpose: every caller is a readiness probe polling for an expected output, and a
    container that is not ready yet fails the exec rather than printing something wrong.
    """
    compose_run = _run("exec", "-T", service, *command, files=files, timeout=120)
    if compose_run.returncode != 0:
        return f"<rc={compose_run.returncode} {compose_run.stderr.strip()}>"
    return compose_run.stdout.strip()


class ReadinessProbe(Protocol):
    def __call__(self) -> str: ...


def _wait_for(
    label: str,
    probe: ReadinessProbe,
    target: str,
    files: tuple[Path, ...],
    *,
    attempts: int = 30,
    delay: float = 2.0,
) -> None:
    """Poll `probe` until it returns `target`; on exhaustion attach the container logs.

    Everything here is a readiness probe: both containers report `running` well before amuled
    listens or uvicorn has bound its socket. Their logs are THE diagnostic, so a failure carries
    them.
    """
    last = "<never ran>"
    for _ in range(attempts):
        last = probe()
        if last == target:
            return
        time.sleep(delay)
    logs = _run("logs", "--no-color", "--tail", "80", files=files, timeout=60)
    raise AssertionError(
        f"{label}: expected {target!r}, last was {last!r}\n--- logs ---\n{logs.stdout}{logs.stderr}"
    )


_WEBUI_HEALTH = (
    "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/health').status)"
)
# From the aMule container: a webui bound to the core's loopback only fails it.
_WEBUI_HEALTH_FROM_ED2K = (
    f"import urllib.request;print(urllib.request.urlopen('http://{_CORE}:8080/health').status)"
)

# The node metrics on the webui's port: "200 True" once the crawler has started.
_METRICS_SHOW_THE_CRAWLER_UP = (
    "import urllib.request;"
    "response = urllib.request.urlopen('http://localhost:8080/metrics');"
    "print(response.status, 'p2pwatch_crawler_up 1.0' in response.read().decode().splitlines())"
)
# No second HTTP server: the 4.x metrics port refuses the connection.
_NO_METRICS_SERVER_ON_9090 = (
    "import errno, socket;"
    "print(socket.socket().connect_ex(('localhost', 9090)) == errno.ECONNREFUSED)"
)

# amuleapi is supervised by amuled, not by s6, so s6-svstat says nothing about it. Read from the
# core, by the service name the core itself uses, its /health proves the wiring.
_AMULEAPI_HEALTH = (
    "import urllib.request;"
    f"print(urllib.request.urlopen('http://{_AMULE}:4711/api/v1/health').status)"
)

# The core's own status reading of amuled: "No reading yet." or an unreachable client prints no.
_DASHBOARD_READS_AMULED = (
    "import urllib.request;"
    "page = urllib.request.urlopen('http://localhost:8080/').read().decode();"
    "print('<dt>API reachable</dt><dd>yes</dd>' in page)"
)


@pytest.fixture
def project_files() -> Iterator[tuple[Path, ...]]:
    """Standalone smoke compose file, a fresh state directory, and the surrounding tear-down.

    The three subdirectories are created HERE, by the invoking user, rather than left to the
    daemon: compose would create a missing bind source as root, which is not the shape an
    operator's `deploy/` has.
    """
    if os.getuid() == 0:
        pytest.fail("run as a non-root user: PUID 0 would pass the data/ ownership check")
    base = (_SMOKE,)
    _down(base)
    shutil.rmtree(_STATE_DIRECTORY, ignore_errors=True)
    for name in _STATE_SUBDIRECTORIES:
        (_STATE_DIRECTORY / name).mkdir(parents=True)
    try:
        yield base
    finally:
        _down(base)
        shutil.rmtree(_STATE_DIRECTORY, ignore_errors=True)


def test_the_harness_hides_everything_but_the_daemon_selectors() -> None:
    env = _docker_env({"DOCKER_CONTEXT": "chosen", "HOME": "/somewhere"}, _SMOKE_ENV)

    assert env["DOCKER_CONTEXT"] == "chosen"
    assert env["PUID"] == str(os.getuid())
    assert "HOME" not in env  # the sanitised environment is what keeps the smoke reproducible


def test_a_chosen_daemon_that_answers_nothing_fails_the_call() -> None:
    """Negative path of the two daemon selectors, which is the only side worth proving.

    Without the allowlist the variable never reaches the CLI: the call quietly lands on the
    machine's default daemon and SUCCEEDS, which is how a run meant for one engine ends up
    exercising another. Pointing it at a socket nothing listens on must therefore fail.
    """
    caller_env = {**os.environ, "DOCKER_HOST": "unix:///nonexistent/p2pwatch-smoke.sock"}
    compose_run = _run("ps", files=(_SMOKE,), timeout=120, caller_env=caller_env)

    assert compose_run.returncode != 0, compose_run.stdout
    assert "p2pwatch-smoke.sock" in compose_run.stderr + compose_run.stdout


@pytest.mark.skipif(_USES_PREBUILT, reason="image prebuilt in CI - nothing to build")
def test_build_succeeds(project_files: tuple[Path, ...]) -> None:
    compose_run = _run("build", files=project_files, timeout=1800)
    assert compose_run.returncode == 0, compose_run.stderr


def _up_until_ed2k_is_healthy(files: tuple[Path, ...]) -> None:
    compose_run = _run("up", "-d", *_BUILD_FLAGS, files=files, timeout=1800)
    assert compose_run.returncode == 0, compose_run.stderr
    # The healthcheck tests s6-svstat's OUTPUT, not its exit code (it exits 0 for a stopped
    # service too). `healthy` therefore means amuled really is up under s6.
    _wait_for("health", lambda: _ps_field(_AMULE, "Health", files), "healthy", files)


def test_the_two_containers_work_together(project_files: tuple[Path, ...]) -> None:
    """Both run, the core reads amuled at `ed2k:4711`, and writes data/ as PUID."""
    _up_until_ed2k_is_healthy(project_files)
    for service in (_CORE, _AMULE):
        state = partial(_ps_field, service, "State", project_files)
        _wait_for(f"{service} state", state, "running", project_files)
    # The core serves the read-only webui in-process, on a bind fixed at 0.0.0.0:8080 in code.
    # Polled from the other container, so no host port is needed.
    _wait_for(
        "webui /health from ed2k",
        lambda: _exec(_AMULE, "python3", "-c", _WEBUI_HEALTH_FROM_ED2K, files=project_files),
        "200",
        project_files,
    )
    _wait_for(
        "node metrics on 8080",
        lambda: _exec(_CORE, "python", "-c", _METRICS_SHOW_THE_CRAWLER_UP, files=project_files),
        "200 True",
        project_files,
    )
    assert _exec(_CORE, "python", "-c", _NO_METRICS_SERVER_ON_9090, files=project_files) == "True"
    _wait_for(
        "amuleapi /health",
        lambda: _exec(_CORE, "python", "-c", _AMULEAPI_HEALTH, files=project_files),
        "200",
        project_files,
    )
    _wait_for(
        "dashboard reading of amuled",
        lambda: _exec(_CORE, "python", "-c", _DASHBOARD_READS_AMULED, files=project_files),
        "True",
        project_files,
        attempts=60,
    )
    # Read in the container: Docker Desktop's file sharing shows every file as the host user's.
    owner = _exec(_CORE, "stat", "-c", "%u", "/data/catalog.db", files=project_files)
    assert owner == str(os.getuid())


_PORT_SYNC_SERVICE = "/etc/services.d/port-sync"
_AMULED_SERVICE = "/etc/services.d/amuled"


def test_port_sync_stays_down_with_port_sync_unset(project_files: tuple[Path, ...]) -> None:
    _up_until_ed2k_is_healthy(project_files)
    time.sleep(30)

    # A run script respawned every second would read `true` wanted up and an updownfor under 2.
    fields = "up,wantedup,normallyup,updownfor"
    up, wantedup, normallyup, updownfor = _exec(
        _AMULE, "s6-svstat", "-o", fields, _PORT_SYNC_SERVICE, files=project_files
    ).split()
    assert (up, wantedup, normallyup) == ("false", "false", "false")
    assert int(updownfor) >= 25
    assert _exec(_AMULE, "s6-svstat", "-o", "up", _AMULED_SERVICE, files=project_files) == "true"


# gluetun's control server at port-sync's default URL: in the vpn variant `ed2k` shares gluetun's
# network namespace, so the stand-in serves its answer from `ed2k`'s own localhost:8000.
_GLUETUN_STAND_IN_ROOT = "/tmp/gluetun-stand-in"
_GLUETUN_STAND_IN_LOG = "/tmp/gluetun-stand-in.log"
_FORWARDED_PORT = 40123

_AMULE_CONF_LISTEN_PORTS = """
import configparser
parser = configparser.RawConfigParser(strict=False)
parser.read("/home/amule/.aMule/amule.conf")
print(parser.get("eMule", "Port", fallback=None), parser.get("eMule", "UDPPort", fallback=None))
"""


def _serve_forwarded_port(port: int, files: tuple[Path, ...]) -> None:
    """Have the stand-in answer `{"port": <port>}`, its file replaced whole."""
    answer = f"{_GLUETUN_STAND_IN_ROOT}/v1/portforward"
    script = (
        f"mkdir -p {_GLUETUN_STAND_IN_ROOT}/v1"
        f" && printf '{{\"port\": {port}}}' > {answer}.tmp && mv {answer}.tmp {answer}"
    )
    assert _exec(_AMULE, "sh", "-c", script, files=files) == ""


def _forwarded_port_requests(files: tuple[Path, ...]) -> int:
    """How many times the stand-in served `/v1/portforward`, from its access log."""
    count = _exec(_AMULE, "grep", "-c", "GET /v1/portforward", _GLUETUN_STAND_IN_LOG, files=files)
    return int(count) if count.isdigit() else 0


def _listen_ports(files: tuple[Path, ...]) -> str:
    """amule.conf's `Port` and `UDPPort`, read in `ed2k`."""
    return _exec(_AMULE, "python3", "-c", _AMULE_CONF_LISTEN_PORTS, files=files)


def _amuled_up_and_pid(files: tuple[Path, ...]) -> str:
    """Whether amuled is up, and its pid."""
    return _exec(_AMULE, "s6-svstat", "-o", "up,pid", _AMULED_SERVICE, files=files)


def test_port_sync_restarts_amuled_on_the_forwarded_port_only_when_it_moved(
    project_files: tuple[Path, ...],
) -> None:
    """The stand-in first serves the port amuled listens on, then another one."""
    _up_until_ed2k_is_healthy(project_files)
    ports_before = _listen_ports(project_files)
    port, _ = ports_before.split()
    up, pid_before = _amuled_up_and_pid(project_files).split()
    assert up == "true"
    _serve_forwarded_port(int(port), project_files)
    serve = f"exec python3 -u -m http.server 8000 -d {_GLUETUN_STAND_IN_ROOT}"
    stand_in = _run(
        "exec",
        "-T",
        "-d",
        _AMULE,
        "sh",
        "-c",
        f"{serve} 2> {_GLUETUN_STAND_IN_LOG}",
        files=project_files,
        timeout=60,
    )
    assert stand_in.returncode == 0, stand_in.stderr
    assert _exec(_AMULE, "s6-svc", "-u", _PORT_SYNC_SERVICE, files=project_files) == ""

    # One round runs at a time: a second request means the first round has finished.
    _wait_for(
        "two rounds of port-sync",
        lambda: str(_forwarded_port_requests(project_files) >= 2),
        "True",
        project_files,
    )
    assert _listen_ports(project_files) == ports_before
    assert _amuled_up_and_pid(project_files) == f"true {pid_before}"

    _serve_forwarded_port(_FORWARDED_PORT, project_files)
    moved = f"{_FORWARDED_PORT} {_FORWARDED_PORT}"
    _wait_for("amule.conf's ports", partial(_listen_ports, project_files), moved, project_files)
    # Written only while amuled is down: up again, it is the process port-sync started.
    amuled_up = partial(
        _exec, _AMULE, "s6-svstat", "-o", "up", _AMULED_SERVICE, files=project_files
    )
    _wait_for("amuled up again", amuled_up, "true", project_files)
    up, pid_after = _amuled_up_and_pid(project_files).split()
    assert (up, pid_after != pid_before) == ("true", True)


def _render(variant: str, tmp_path: Path) -> Any:
    """`docker compose config` of a copy of deploy/'s compose files, switched to `variant`.

    Copied, so the `.env` it needs never lands in deploy/, where a developer's secrets live. No
    PUID in the process environment: the included file can only take it from the parent's `.env`.
    """
    for source in _DEPLOY.glob("**/*compose.yml"):
        copy = tmp_path / source.relative_to(_DEPLOY)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(source.read_text())
    compose = tmp_path / "compose.yml"
    text = compose.read_text()
    assert text.count(_DIRECT_INCLUDE) == 1, "compose.yml must name the direct include once"
    compose.write_text(text.replace(_DIRECT_INCLUDE, f"ed2k/{variant}.compose.yml"))
    (tmp_path / ".env").write_text("".join(f"{k}={v}\n" for k, v in _RENDER_DOTENV.items()))

    compose_run = subprocess.run(
        ["docker", "compose", "-f", str(compose), "config", "--format", "json"],
        cwd=tmp_path,
        env=_docker_env(os.environ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert compose_run.returncode == 0, compose_run.stderr
    rendered = json.loads(compose_run.stdout)
    assert not rendered.get("volumes"), f"named volumes are gone, got {rendered['volumes']}"
    return rendered["services"]


def _binds(service: Any) -> dict[str, tuple[Path, bool]]:
    """Each bind mount of a rendered service: target -> (source, read-only)."""
    return {v["target"]: (Path(v["source"]), bool(v.get("read_only"))) for v in service["volumes"]}


def _ports(service: Any) -> set[tuple[int, str]]:
    """Each port a rendered service publishes: (container port, protocol)."""
    return {(p["target"], p["protocol"]) for p in service.get("ports", [])}


@pytest.mark.parametrize("variant", _VARIANTS)
def test_the_deploy_layout_renders(variant: str, tmp_path: Path) -> None:
    """The core and `ed2k` render from deploy/compose.yml, `ed2k` from its own directory."""
    services = _render(variant, tmp_path)
    ed2k_directory = tmp_path / "ed2k"
    core, ed2k = services[_CORE], services[_AMULE]

    assert ed2k["environment"]["PUID"] == _RENDER_DOTENV["PUID"]
    # Interpolated by the included file alone: the core takes AMULE_API_PASSWORD.
    assert ed2k["environment"]["AMULE_EC_PASSWORD"] == _RENDER_DOTENV["AMULE_EC_PASSWORD"]
    assert core["user"] == f"{_RENDER_DOTENV['PUID']}:{_RENDER_DOTENV['PGID']}"
    for source, _ in _binds(ed2k).values():
        assert source.is_relative_to(ed2k_directory), f"{source} is outside {ed2k_directory}"
    assert _binds(core)["/downloads"] == (ed2k_directory / "downloads", True)
    assert _binds(core)["/data"] == (tmp_path / "data", False)
    assert "network_mode" not in core  # the core stays outside the tunnel
    assert _ports(core) == {(8080, "tcp")}

    if variant == "direct":
        assert set(services) == {_CORE, _AMULE}
        assert _ports(ed2k) == {(4711, "tcp"), (4662, "tcp"), (4672, "udp")}
        return
    assert set(services) == {_CORE, _AMULE, "ed2k-gluetun"}
    aliases = services["ed2k-gluetun"]["networks"]["default"]["aliases"]
    assert _AMULE in aliases
    assert ed2k["network_mode"] == "service:ed2k-gluetun"
    assert ed2k["environment"]["PORT_SYNC"] == _RENDER_DOTENV["VPN_PORT_FORWARDING"]
    gluetun = services["ed2k-gluetun"]
    assert _ports(gluetun) == {(4711, "tcp")}
    assert "ports" not in ed2k


# --- Completion scenario (scope-reduction spec §4) ---------------------------------------------
#
# amuled's IncomingDir, written by the startup one-shot into amule.conf. A file dropped there is
# hashed and shared at the next amuled start, which is how we obtain a REAL ed2k hash without
# ever computing one ourselves.
_INCOMING_DIRECTORY = "/downloads/incoming"
_SEEDED_TARGET = "062A"
_SEEDED_SIZE = 65536

# Read from the core, at the address fixed in code (`_AMULE_API_ADDRESS`).
_API_HOST, _API_PORT = _AMULE, 4711

_SHARED_HASHES = f"""
import asyncio, json
from datetime import timedelta
import httpx
from p2pwatch.adapters.driven.asyncio_monotonic_clock import AsyncioMonotonicClock
from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient

async def main() -> None:
    client = AmuleApiClient(
        {_API_HOST!r},
        {_API_PORT},
        {_API_PASSWORD!r},
        timeout_seconds=10.0,
        page_size=500,
        progress_poll_interval=timedelta(seconds=5),
        monotonic_clock=AsyncioMonotonicClock(),
        transport_factory=httpx.AsyncHTTPTransport,
    )
    completed = [d.file.native_id for d in await client.downloads() if d.completed]
    print(json.dumps(sorted(completed)))
    await client.close()

asyncio.run(main())
"""

_SEED_ROW = f"""
import datetime, sqlite3, sys
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.domain.file_key import FileKey, Network
now_micros = instant_to_micros(datetime.datetime.now(datetime.UTC))
file = FileKey(Network.ED2K, sys.argv[1])
connection = sqlite3.connect("/data/local.db", timeout=30)
connection.execute(
    "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at_micros,"
    " size_bytes, latest_seen_at_micros)"
    " VALUES (?, ?, ?, {_SEEDED_TARGET!r}, 'downloading', ?, {_SEEDED_SIZE}, ?)",
    (file.file_id, file.network, file.native_id, now_micros, now_micros),
)
connection.commit()
"""

_READ_ROW = """
import sqlite3, sys
connection = sqlite3.connect("/data/local.db", timeout=30)
connection.row_factory = sqlite3.Row
row = connection.execute(
    "SELECT state, completed_at_micros IS NOT NULL AS completed FROM downloads WHERE native_id = ?",
    (sys.argv[1],),
).fetchone()
print(row["state"], bool(row["completed"]))
"""


def _exec_python(script: str, *args: str, files: tuple[Path, ...]) -> str:
    """Run `script` with the container's python and return its stdout (fails loudly)."""
    compose_run = _run("exec", "-T", _CORE, "python", "-c", script, *args, files=files, timeout=120)
    assert compose_run.returncode == 0, f"{compose_run.stdout}{compose_run.stderr}"
    return compose_run.stdout.strip()


def _shared_hashes(files: tuple[Path, ...]) -> frozenset[str] | None:
    """Hashes amuled currently shares, read over the API from the core.

    `None` means the call itself did not complete. That is a READINESS state, not a result:
    `s6-svc -r` takes amuleapi down with amuled and brings both back, and in between the API
    answers `503 ec_unavailable` or nothing at all. Callers poll on it.
    """
    output = _exec(_CORE, "python", "-c", _SHARED_HASHES, files=files)
    try:
        return frozenset(json.loads(output))
    except json.JSONDecodeError:
        return None


def _wait_new_shared_hash(
    before: frozenset[str], files: tuple[Path, ...], *, attempts: int = 20, delay: float = 2.0
) -> str:
    """Poll until exactly one hash appeared in amuled's shared list, and return it.

    Called right after `s6-svc -r`, so it is the readiness probe for the restart TOO: amuled is
    still shutting down for the first attempts (amuleapi refuses or resets), then comes back and
    hashes the IncomingDir asynchronously. A failed amuleapi call is therefore a poll iteration,
    not a failure.
    The "exactly one" bound is what identifies OUR file: the smoke amuled shares nothing else at
    that point (its only queue entry has no sources and no bytes, so it is not shared yet).
    """
    appeared: frozenset[str] = frozenset()
    for _ in range(attempts):
        current = _shared_hashes(files)
        if current is not None:
            appeared = current - before
            if len(appeared) == 1:
                return next(iter(appeared))
        time.sleep(delay)
    raise AssertionError(f"expected exactly one new shared hash, got {sorted(appeared)}")


def test_a_file_amuled_shares_is_recorded_completed(project_files: tuple[Path, ...]) -> None:
    """End to end: amuled shares a file that left the queue, the crawler completes and notifies.

    Drives the running containers rather than an in-process cycle, so the whole path (real HTTP
    call from the core to `ed2k`, real amuled behind amuleapi, real local.db on a bind mount) is
    exercised without building a parallel harness. The ed2k hash is never computed here; amuled
    computes it and we read it back over the API, which is what makes seeding a matching row
    possible at all.
    """
    _up_until_ed2k_is_healthy(project_files)
    _wait_for(
        "webui /health",
        lambda: _exec(_CORE, "python", "-c", _WEBUI_HEALTH, files=project_files),
        "200",
        project_files,
    )

    before = _shared_hashes(project_files)
    assert before is not None, "amuleapi must answer before the restart"
    drop = _run(
        "exec",
        "-T",
        _AMULE,
        "sh",
        "-c",
        f"head -c {_SEEDED_SIZE} /dev/urandom > {_INCOMING_DIRECTORY}/p2pwatch-smoke.bin",
        files=project_files,
        timeout=120,
    )
    assert drop.returncode == 0, f"{drop.stdout}{drop.stderr}"
    # amuled only scans its IncomingDir at startup, so the rescan is an s6 restart in `ed2k`.
    restart = _run(
        "exec",
        "-T",
        _AMULE,
        "s6-svc",
        "-r",
        "/etc/services.d/amuled",
        files=project_files,
        timeout=60,
    )
    assert restart.returncode == 0, f"{restart.stdout}{restart.stderr}"
    native_id = _wait_new_shared_hash(before, project_files)

    # The file is shared and was never in the download queue: the completion signal is complete.
    _exec_python(_SEED_ROW, native_id, files=project_files)
    _wait_for(
        f"download {native_id}",
        lambda: _exec(_CORE, "python", "-c", _READ_ROW, native_id, files=project_files),
        "completed True",
        project_files,
    )

    # The completion also reached the observability pipeline (the notification, target-labelled).
    logs = _run("logs", "--no-color", _CORE, files=project_files, timeout=60)
    assert f"download completed: {_SEEDED_TARGET}" in logs.stdout, logs.stdout[-4000:]
