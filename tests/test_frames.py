"""The wire format: these exact bytes are what `Frames.kt` on the device reads and writes."""

from __future__ import annotations

import asyncio

import pytest

from halecho import frames


def _reader(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


def test_json_frame_bytes_are_pinned():
    assert frames.encode_json({"type": "ping", "t": 1}) == (
        b"\x00\x00\x00\x15\x01" + b'{"type":"ping","t":1}'
    )


def test_audio_frame_bytes_are_pinned():
    assert frames.encode_audio(7, 2, b"\x01\x02") == b"\x00\x00\x00\x0a\x02" + bytes(
        [0, 0, 0, 7, 0, 0, 0, 2, 1, 2]
    )


def test_term_frame_bytes_are_pinned():
    assert frames.encode_term(5, b"\x1b[") == b"\x00\x00\x00\x06\x04" + bytes(
        [0, 0, 0, 5, 0x1B, 0x5B]
    )


def test_json_is_ascii_escaped():
    assert b"\\u2014" in frames.encode_json({"type": "say", "text": "\u2014"})


async def test_frames_round_trip():
    data = frames.encode_json({"type": "hello"}) + frames.encode_blob(3, b"abc")
    reader = _reader(data)
    assert (await frames.read_frame(reader)).json() == {"type": "hello"}
    assert (await frames.read_frame(reader)).blob() == (3, b"abc")


async def test_oversized_header_is_refused_before_reading_the_payload():
    header = frames.HEADER.pack(frames.MAX_PAYLOAD + 1, frames.JSON)
    with pytest.raises(frames.FrameError):
        await frames.read_frame(_reader(header))


async def test_unknown_kind_is_refused():
    with pytest.raises(frames.FrameError):
        await frames.read_frame(_reader(frames.HEADER.pack(0, 9)))


def test_json_without_a_type_is_refused():
    with pytest.raises(frames.FrameError):
        frames.Frame(frames.JSON, b'{"t":1}').json()
