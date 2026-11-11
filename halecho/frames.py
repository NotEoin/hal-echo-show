"""The wire format shared with the Android app: length-prefixed frames of four kinds.

    frame = length (u32, big endian) | kind (u8) | payload (length bytes)

- `JSON`: one UTF-8 JSON object with a `type` key (the messages are listed in
  `docs/dev/protocol.md`);
- `AUDIO`: turn id (u32) | sequence (u32) | 16-bit little-endian mono PCM;
- `BLOB`: transfer id (u32) | file bytes, for models and app updates;
- `TERM`: terminal id (u32) | bytes: a program's output to the device, or the device's touches
  and keys back to the program, for the terminal screens.

`Frames.kt` in the app is the other implementation; `tests/test_frames.py` pins the bytes.
"""

from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import dataclass
from typing import Any

HEADER = struct.Struct(">IB")
AUDIO_HEADER = struct.Struct(">II")
BLOB_HEADER = struct.Struct(">I")
# 30 s of 16 kHz PCM16 is 960 KB, the longest utterance a device sends in one frame
MAX_PAYLOAD = 1 << 20

JSON, AUDIO, BLOB, TERM = 1, 2, 3, 4
KINDS = (JSON, AUDIO, BLOB, TERM)


class FrameError(ValueError):
    """A frame is malformed or larger than `MAX_PAYLOAD`."""


@dataclass(frozen=True)
class Frame:
    """One decoded frame."""

    kind: int
    payload: bytes

    def json(self) -> dict[str, Any]:
        """The message of a `JSON` frame.

        Raises:
            FrameError: the frame is another kind, or not a JSON object with a string `type`.
        """
        if self.kind != JSON:
            raise FrameError(f"expected a JSON frame, got kind {self.kind}")
        try:
            msg = json.loads(self.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FrameError(f"bad JSON frame: {exc}") from exc
        if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
            raise FrameError("a JSON frame must be an object with a string 'type'")
        return msg

    def audio(self) -> tuple[int, int, bytes]:
        """The turn id, sequence number and PCM of an `AUDIO` frame."""
        if self.kind != AUDIO or len(self.payload) < AUDIO_HEADER.size:
            raise FrameError("not an audio frame")
        turn, seq = AUDIO_HEADER.unpack_from(self.payload)
        return turn, seq, self.payload[AUDIO_HEADER.size :]

    def blob(self) -> tuple[int, bytes]:
        """The transfer id and bytes of a `BLOB` frame."""
        if self.kind != BLOB or len(self.payload) < BLOB_HEADER.size:
            raise FrameError("not a blob frame")
        (transfer,) = BLOB_HEADER.unpack_from(self.payload)
        return transfer, self.payload[BLOB_HEADER.size :]

    def term(self) -> tuple[int, bytes]:
        """The terminal id and bytes of a `TERM` frame."""
        if self.kind != TERM or len(self.payload) < BLOB_HEADER.size:
            raise FrameError("not a terminal frame")
        (term,) = BLOB_HEADER.unpack_from(self.payload)
        return term, self.payload[BLOB_HEADER.size :]


def encode(kind: int, payload: bytes) -> bytes:
    """One frame, ready to write."""
    if kind not in KINDS:
        raise FrameError(f"unknown frame kind {kind}")
    if len(payload) > MAX_PAYLOAD:
        raise FrameError(f"payload of {len(payload)} bytes exceeds {MAX_PAYLOAD}")
    return HEADER.pack(len(payload), kind) + payload


def encode_json(msg: dict[str, Any]) -> bytes:
    """A `JSON` frame; ASCII-escaped so the bytes are the same on both ends."""
    return encode(JSON, json.dumps(msg, separators=(",", ":")).encode("ascii"))


def encode_audio(turn: int, seq: int, pcm: bytes) -> bytes:
    """An `AUDIO` frame."""
    return encode(AUDIO, AUDIO_HEADER.pack(turn, seq) + pcm)


def encode_blob(transfer: int, data: bytes) -> bytes:
    """A `BLOB` frame."""
    return encode(BLOB, BLOB_HEADER.pack(transfer) + data)


def encode_term(term: int, data: bytes) -> bytes:
    """A `TERM` frame."""
    return encode(TERM, BLOB_HEADER.pack(term) + data)


async def read_frame(reader: asyncio.StreamReader) -> Frame:
    """Reads one frame.

    Raises:
        asyncio.IncompleteReadError: the peer closed the connection.
        FrameError: the header names an unknown kind or an oversized payload.
    """
    length, kind = HEADER.unpack(await reader.readexactly(HEADER.size))
    if kind not in KINDS:
        raise FrameError(f"unknown frame kind {kind}")
    if length > MAX_PAYLOAD:
        raise FrameError(f"payload of {length} bytes exceeds {MAX_PAYLOAD}")
    return Frame(kind, await reader.readexactly(length))
