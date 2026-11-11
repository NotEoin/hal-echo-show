"""The bridge: accepts paired devices over TLS and hands each one to a `DeviceSession`.

The TLS context is rebuilt from the registry for every connection, so `hal-echo pair` and
`hal-echo unpair` take effect without a restart. A local control socket, readable by the
owner only, lets `hal-echo say`, `status` and `push-update` reach the running bridge.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
import ssl
from pathlib import Path
from typing import Any

from . import config, tls
from .backend import Backend
from .discovery import Announcer
from .floor import Floor
from .identity import Identity
from .registry import Registry
from .session import DeviceSession

log = logging.getLogger(__name__)

HANDSHAKE_TIMEOUT_S = 15.0
CONTROL_TIMEOUT_S = 10.0
CONTROL_LIMIT_BYTES = 64 * 1024
SOCKET_NAME = "hal-echo-show.sock"


def control_path() -> Path:
    """The control socket: in `$XDG_RUNTIME_DIR` when there is one, else the state dir."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime) if runtime else config.private_dir(config.state_dir())
    return base / SOCKET_NAME


def server_name(settings: Any) -> str:
    """`server.name`, or the PC's host name."""
    return str(settings.get("server.name") or socket.gethostname())


class Bridge:
    """Serves every paired device until cancelled."""

    def __init__(
        self, settings: Any, identity: Identity, registry: Registry, backend: Backend
    ) -> None:
        self.settings = settings
        self.identity = identity
        self.registry = registry
        self.backend = backend
        self.floor = Floor(float(settings.get("floor.window_ms", 350)) / 1000)
        self.sessions: dict[str, DeviceSession] = {}
        self.name = server_name(settings)
        self.port = 0

    async def serve(self, ready: asyncio.Event | None = None) -> None:
        """Listens on `server.host:server.port` and the control socket until cancelled."""
        host, port = self.settings.get("server.host"), int(self.settings.get("server.port"))
        server = await asyncio.start_server(self._accept, host, port)
        self.port = server.sockets[0].getsockname()[1]
        ctl_path = control_path()
        ctl_path.unlink(missing_ok=True)
        old_umask = os.umask(0o177)  # the socket is created owner-only, with no window
        try:
            control = await asyncio.start_unix_server(
                self._control, ctl_path, limit=CONTROL_LIMIT_BYTES
            )
        finally:
            os.umask(old_umask)
        announce = (
            Announcer(self.name, port, self.identity.fingerprint, False, 0)
            if self.settings.get("server.advertise")
            else contextlib.nullcontext()
        )
        log.info("bridge listening on %s:%s as '%s'", host, port, self.name)
        async with server, control, announce:
            if ready is not None:
                ready.set()
            try:
                await asyncio.Future()
            finally:
                for session in list(self.sessions.values()):
                    session.writer.close()
                ctl_path.unlink(missing_ok=True)

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        address = str(writer.get_extra_info("peername", ("?",))[0])
        ctx = tls.server_context(self.identity, self.registry.all())
        try:
            await writer.start_tls(ctx, ssl_handshake_timeout=HANDSHAKE_TIMEOUT_S)
            device = tls.pinned_device(writer.get_extra_info("ssl_object"), self.registry)
        except (ssl.SSLError, ConnectionError, TimeoutError) as exc:
            log.warning("refused %s: %s", address, exc)
            writer.close()
            return
        self.registry.seen_at(device.id, address)
        old = self.sessions.get(device.id)
        if old is not None:
            old.writer.close()  # the device reconnected; its old connection is dead
            await old.closed.wait()
        session = DeviceSession(
            device, reader, writer, self.backend, self.settings, self.floor, self.name
        )
        self.sessions[device.id] = session
        try:
            await session.run()
        finally:
            if self.sessions.get(device.id) is session:
                del self.sessions[device.id]

    async def _control(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), CONTROL_TIMEOUT_S)
            reply = await self._command(json.loads(line or b"{}"))
        except (json.JSONDecodeError, KeyError, ValueError, TimeoutError) as exc:
            reply = {"ok": False, "error": str(exc)}
        writer.write(json.dumps(reply).encode() + b"\n")
        await writer.drain()
        writer.close()

    def _targets(self, key: str | None) -> list[DeviceSession]:
        if not key:
            return list(self.sessions.values())
        dev = self.registry.find(key)
        return [self.sessions[dev.id]] if dev.id in self.sessions else []

    async def _command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        action = cmd.get("cmd")
        if action == "status":
            return {
                "ok": True,
                "connected": {
                    s.device.id: {"muted": s.muted, "awake": s.awake}
                    for s in self.sessions.values()
                },
            }
        if action == "say":
            targets = self._targets(cmd.get("device"))
            for session in targets:
                session.say(str(cmd["text"]))
            return {"ok": bool(targets), "devices": [s.device.name for s in targets]}
        if action == "push_update":
            path = Path(str(cmd["path"]))
            if not path.is_file() or path.stat().st_size == 0:
                return {"ok": False, "error": f"{path} is not a file"}
            targets = self._targets(cmd.get("device"))
            for session in targets:
                await session.send_file(path, "update", path.name)
            return {"ok": bool(targets), "devices": [s.device.name for s in targets]}
        return {"ok": False, "error": f"unknown command {action!r}"}


async def control_request(cmd: dict[str, Any], timeout_s: float = 300.0) -> dict[str, Any]:
    """Sends one command to the running bridge and returns its reply.

    Raises:
        ConnectionError: the bridge is not running.
    """
    try:
        reader, writer = await asyncio.open_unix_connection(control_path())
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise ConnectionError("the bridge is not running: start `hal-echo serve`") from exc
    writer.write(json.dumps(cmd).encode() + b"\n")
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout_s)
    writer.close()
    return json.loads(line)
