"""One-time pairing: the code on the Echo's screen, typed on the PC, authenticates both keys.

    device -> pc   pair_hello    {sid, name, cert, y}     the device is the CPace initiator
    (the person types the code shown on the device)
    pc -> device   pair_reply    {name, cert, y, tag}
    device -> pc   pair_confirm  {tag}
    pc -> device   pair_done     {id, name, mode, port}   or pair_failed {reason}

Each side's associated data is its own certificate, so a matching confirmation tag proves
that both certificates came from someone who knew the code. The listener is open only while
`hal-echo pair` runs and closes after `pairing.max_attempts` wrong codes, so an attacker gets
that many one-in-a-million guesses. The device shows a fresh code for every attempt.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from . import frames
from .cpace import CPace, PairingFailed, lv_cat
from .identity import Identity
from .registry import Device, Registry, clean_name

log = logging.getLogger(__name__)

PAIRING_VERSION = 1
CI = lv_cat(b"hal-echo-show device", b"hal-echo-show pc")
CODE_DIGITS = 6
SID_BYTES = 16
STEP_TIMEOUT_S = 30.0  # a device answers each step at once; this only bounds a dead peer
MAX_CERT_BYTES = 4096  # a P-256 certificate is under 1 KB

#: Called with the device's name and address; returns the typed code, or None to refuse.
AskCode = Callable[[str, str], Awaitable[str | None]]


def normalise_code(code: str) -> bytes:
    """The code as the bytes both sides hash: its digits only, so "123 456" works.

    Raises:
        PairingFailed: the code does not have `CODE_DIGITS` digits.
    """
    digits = re.sub(r"\D", "", code)
    if len(digits) != CODE_DIGITS:
        raise PairingFailed(f"the code has {CODE_DIGITS} digits")
    return digits.encode("ascii")


def _hex_field(msg: dict, key: str, size: int | None = None, limit: int = 64) -> bytes:
    try:
        value = bytes.fromhex(str(msg[key]))
    except (KeyError, ValueError) as exc:
        raise PairingFailed(f"missing or malformed '{key}'") from exc
    if (size is not None and len(value) != size) or len(value) > limit:
        raise PairingFailed(f"'{key}' has the wrong length")
    return value


async def _read_json(reader: asyncio.StreamReader, expected: str) -> dict:
    msg = (await asyncio.wait_for(frames.read_frame(reader), STEP_TIMEOUT_S)).json()
    if msg["type"] != expected:
        raise PairingFailed(f"expected '{expected}', got '{msg['type']}'")
    return msg


@dataclass
class PairingServer:
    """The PC side of pairing, run by `hal-echo pair`."""

    identity: Identity
    registry: Registry
    ask_code: AskCode
    mode: str
    server_name: str
    server_port: int
    max_attempts: int = 3

    def __post_init__(self) -> None:
        self._busy = asyncio.Lock()
        self._failures = 0
        self._code_asked = False
        self.port = 0
        self.listening = asyncio.Event()
        self._done: asyncio.Future[Device | None] = asyncio.get_running_loop().create_future()

    async def run(self, host: str, port: int, window_s: float) -> Device | None:
        """Listens until one device pairs, the attempts run out or the window closes."""
        server = await asyncio.start_server(self._handle, host, port)
        self.port = server.sockets[0].getsockname()[1]
        self.listening.set()
        try:
            async with server:
                return await asyncio.wait_for(self._done, window_s)
        except TimeoutError:
            log.info("pairing window closed")
            return None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        address = str(writer.get_extra_info("peername", ("?",))[0])
        if self._busy.locked() or self._done.done():
            writer.close()  # one pairing at a time
            return
        async with self._busy:
            self._code_asked = False
            try:
                dev = await self._pair(reader, writer, address)
            except PairingFailed as exc:
                await _send_quietly(writer, {"type": "pair_failed", "reason": str(exc)})
                self._failed(address, exc)
                return
            except (
                TimeoutError,
                asyncio.IncompleteReadError,
                ConnectionError,
                frames.FrameError,
            ) as exc:
                # A peer that hangs up once it has the PC's tag has still spent a guess
                if self._code_asked:
                    self._failed(address, exc)
                else:
                    log.warning("pairing with %s broke off: %s", address, exc)
                return
            finally:
                writer.close()
            if not self._done.done():
                self._done.set_result(dev)

    def _failed(self, address: str, exc: Exception) -> None:
        self._failures += 1
        log.warning("pairing with %s failed: %s", address, exc)
        if self._failures >= self.max_attempts and not self._done.done():
            log.warning("%d failed attempts: pairing stopped", self._failures)
            self._done.set_result(None)

    async def _pair(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, address: str
    ) -> Device:
        hello = await _read_json(reader, "pair_hello")
        if hello.get("v") != PAIRING_VERSION:
            raise PairingFailed(f"protocol version {hello.get('v')} is not {PAIRING_VERSION}")
        sid = _hex_field(hello, "sid", SID_BYTES)
        device_cert = _hex_field(hello, "cert", limit=MAX_CERT_BYTES)
        device_y = _hex_field(hello, "y", 32)
        name = clean_name(str(hello.get("name", "")))
        self._code_asked = True
        code = await self.ask_code(name, address)
        if code is None:
            raise PairingFailed("refused on the PC")
        own = CPace(normalise_code(code), CI, sid, self.identity.cert_der)
        keys = own.finish(device_y, device_cert, initiator=False)
        writer.write(
            frames.encode_json(
                {
                    "type": "pair_reply",
                    "name": self.server_name,
                    "cert": self.identity.cert_der.hex(),
                    "y": own.message.hex(),
                    "tag": keys.own_tag.hex(),
                }
            )
        )
        await writer.drain()
        confirm = await _read_json(reader, "pair_confirm")
        keys.check(_hex_field(confirm, "tag", 64))
        dev = self.registry.add(name, self.mode, device_cert)
        self.registry.seen_at(dev.id, address)
        writer.write(
            frames.encode_json(
                {
                    "type": "pair_done",
                    "id": dev.id,
                    "name": dev.name,
                    "mode": dev.mode,
                    "port": self.server_port,
                }
            )
        )
        await writer.drain()
        log.info("paired %s (%s) at %s", dev.name, dev.mode, address)
        return dev


async def _send_quietly(writer: asyncio.StreamWriter, msg: dict) -> None:
    try:
        writer.write(frames.encode_json(msg))
        await asyncio.wait_for(writer.drain(), STEP_TIMEOUT_S)
    except (ConnectionError, TimeoutError):
        log.debug("could not tell the device that pairing failed")


@dataclass(frozen=True)
class Paired:
    """What a device keeps after pairing."""

    pc_cert_der: bytes
    pc_name: str
    device_id: str
    port: int


async def pair_as_device(host: str, port: int, code: str, name: str, cert_der: bytes) -> Paired:
    """The device side, as the Android app runs it; used by the tests and the simulator.

    Raises:
        PairingFailed: the PC used another code or refused.
    """
    reader, writer = await asyncio.open_connection(host, port)
    try:
        sid = os.urandom(SID_BYTES)
        own = CPace(normalise_code(code), CI, sid, cert_der)
        writer.write(
            frames.encode_json(
                {
                    "type": "pair_hello",
                    "v": PAIRING_VERSION,
                    "sid": sid.hex(),
                    "name": name,
                    "cert": cert_der.hex(),
                    "y": own.message.hex(),
                }
            )
        )
        await writer.drain()
        reply = (await frames.read_frame(reader)).json()
        if reply["type"] == "pair_failed":
            raise PairingFailed(str(reply.get("reason")))
        if reply["type"] != "pair_reply":
            raise PairingFailed(f"unexpected '{reply['type']}'")
        pc_cert = _hex_field(reply, "cert", limit=MAX_CERT_BYTES)
        keys = own.finish(_hex_field(reply, "y", 32), pc_cert, initiator=True)
        keys.check(_hex_field(reply, "tag", 64))
        writer.write(frames.encode_json({"type": "pair_confirm", "tag": keys.own_tag.hex()}))
        await writer.drain()
        done = await _read_json(reader, "pair_done")
        return Paired(pc_cert, str(reply.get("name", "")), str(done["id"]), int(done["port"]))
    finally:
        writer.close()
