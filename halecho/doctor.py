"""`hal-echo doctor`: checks each part of the PC side and says how to fix what fails."""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import config, models, sodium
from .registry import Registry

OK, WARN, FAIL = "ok", "warn", "FAIL"
STATUS_TIMEOUT_S = 5.0
# World-readable, unlike `ufw status`, which needs root
UFW_CONF = Path("/etc/ufw/ufw.conf")

#: One check's outcome: what was checked, its status, and the detail or fix.
Result = tuple[str, str, str]


def check_libsodium() -> Result:
    """libsodium with ristretto255, needed for pairing."""
    problem = sodium.available()
    return "libsodium", FAIL if problem else OK, problem or "ristretto255 available"


def check_hal_voice() -> Result:
    """hal-voice importable from this environment."""
    if importlib.util.find_spec("halvoice") is not None:
        return "hal-voice", OK, "importable"
    return "hal-voice", FAIL, "not installed in this environment; see the README"


def check_identity() -> Result:
    """The PC's key, created by the first `hal-echo pair`."""
    key = config.config_dir() / "pc-key.pem"
    if key.exists():
        return "identity", OK, str(key)
    return "identity", WARN, "not created yet; `hal-echo pair` creates it"


def check_devices() -> Result:
    """At least one paired device."""
    devices = Registry().all()
    detail = ", ".join(f"{d.name} ({d.mode})" for d in devices) or "none paired"
    return "devices", OK if devices else WARN, detail


def bridge_status() -> dict | None:
    """The running bridge's status, or None when it is not running."""
    from .server import control_request

    try:
        return asyncio.run(control_request({"cmd": "status"}, STATUS_TIMEOUT_S))
    except (ConnectionError, OSError, TimeoutError):
        return None


def port_free(host: str, port: int) -> bool:
    """True when nothing else listens on `host:port`."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def check_bridge(settings: Any) -> Iterator[Result]:
    """The bridge's state, and its port when it is not running."""
    status = bridge_status()
    if status is not None:
        yield "bridge", OK, f"running, {len(status.get('connected', {}))} device(s) connected"
        return
    yield "bridge", WARN, "not running"
    port = int(settings.get("server.port"))
    if port_free(str(settings.get("server.host")), port):
        yield "port", OK, f"{port} free"
    else:
        yield "port", FAIL, f"{port} in use by another program"


def check_models(settings: Any) -> Iterator[Result]:
    """The configured models: known to the catalogue, and cached or not."""
    for name in (settings.get("listener.stt_model"), settings.get("listener.wake_model")):
        try:
            model = models.get(str(name))
        except models.ModelError as exc:
            yield "model", FAIL, str(exc)
            continue
        if models.cached_path(model).exists():
            yield f"model {name}", OK, "cached"
        else:
            yield f"model {name}", WARN, "downloaded on first request, or run `hal-echo models`"


def check_firewall(conf: Path = UFW_CONF) -> Result | None:
    """Whether ufw is on; None when ufw is not installed."""
    if not shutil.which("ufw") or not conf.exists():
        return None
    enabled = any(line.strip().lower() == "enabled=yes" for line in conf.read_text().splitlines())
    if enabled:
        return "firewall", OK, "ufw is on: `hal-echo firewall` prints the rules for each device"
    return (
        "firewall",
        WARN,
        "ufw is installed but off, so its rules do nothing; see docs/howto/set-up-the-echo.md",
    )


def results(settings: Any) -> list[Result]:
    """Every check, in the order `run` prints them."""
    out = [check_libsodium(), check_hal_voice(), check_identity(), check_devices()]
    out += check_bridge(settings)
    out += check_models(settings)
    firewall = check_firewall()
    if firewall is not None:
        out.append(firewall)
    return out


def run(settings: Any) -> int:
    """Prints one line per check; returns 1 when any check fails."""
    checks = results(settings)
    for label, status, detail in checks:
        print(f"[{status:>4}] {label}: {detail}")
    return 1 if any(status == FAIL for _, status, _ in checks) else 0
