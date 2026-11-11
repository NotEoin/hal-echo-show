"""The Hal pack's tools: speak through the Echo devices, and list them.

They reach the running bridge over its control socket, so they work only while
`hal-echo serve` runs, and raise `RuntimeError` with the fix when it does not.
"""

from __future__ import annotations

import asyncio

from .registry import Registry
from .server import control_request

CONTROL_TIMEOUT_S = 30.0
MAX_TEXT_CHARS = 500  # the same limit as hal-voice's voice_say


def say(text: str, device: str | None = None) -> dict[str, list[str]]:
    """Speaks `text` in HAL's voice on one device, or on every connected one."""
    text = text.strip()
    if not text or len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"text must be 1 to {MAX_TEXT_CHARS} characters")
    try:
        reply = asyncio.run(
            control_request({"cmd": "say", "text": text, "device": device}, CONTROL_TIMEOUT_S)
        )
    except ConnectionError as exc:
        raise RuntimeError(str(exc)) from exc
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error") or "no connected device matched")
    return {"spoken_on": reply.get("devices", [])}


def devices() -> list[dict[str, str | bool]]:
    """The paired devices: name, mode, and whether each is connected now."""
    try:
        status = asyncio.run(control_request({"cmd": "status"}, CONTROL_TIMEOUT_S))
        connected = status.get("connected", {})
    except ConnectionError:
        connected = {}
    return [
        {"name": d.name, "mode": d.mode, "connected": d.id in connected} for d in Registry().all()
    ]
