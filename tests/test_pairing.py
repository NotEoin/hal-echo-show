"""Pairing: the right code pairs both ways, and every wrong attempt is spent and counted."""

from __future__ import annotations

import asyncio

import pytest

from halecho import frames, sodium
from halecho.cpace import PairingFailed
from halecho.identity import load_or_create
from halecho.pairing import PairingServer, normalise_code, pair_as_device
from halecho.registry import Registry

from fakedevice import FakeDevice

pytestmark = pytest.mark.skipif(sodium.available() is not None, reason="needs libsodium")

CODE = "482 913"


def _server(codes: list[str | None], max_attempts: int = 3) -> PairingServer:
    async def ask(_name: str, _address: str) -> str | None:
        return codes.pop(0)

    return PairingServer(
        load_or_create(), Registry(), ask, "personal", "test-pc", 47800, max_attempts
    )


async def _start(server: PairingServer) -> asyncio.Task:
    task = asyncio.create_task(server.run("127.0.0.1", 0, 10))
    await server.listening.wait()
    return task


def test_codes_are_normalised_to_six_digits():
    assert normalise_code("482 913") == b"482913"
    assert normalise_code("482-913") == b"482913"
    with pytest.raises(PairingFailed):
        normalise_code("12345")


async def test_matching_code_pairs_and_pins_both_certificates(tmp_path):
    server = _server([CODE])
    task = await _start(server)
    device = FakeDevice(tmp_path)
    paired = await pair_as_device("127.0.0.1", server.port, "482913", "Bedroom", device.cert_der)
    dev = await task
    assert dev is not None and dev.name == "Bedroom" and dev.mode == "personal"
    assert dev.cert_der == device.cert_der
    assert paired.pc_cert_der == load_or_create().cert_der
    assert paired.device_id == dev.id
    assert Registry().find("bedroom").last_address == "127.0.0.1"


async def test_wrong_code_fails_on_the_device_and_pairs_nothing(tmp_path):
    server = _server(["111111", CODE])
    task = await _start(server)
    device = FakeDevice(tmp_path)
    with pytest.raises(PairingFailed):
        await pair_as_device("127.0.0.1", server.port, CODE, "Kitchen", device.cert_der)
    assert Registry().all() == []
    await pair_as_device("127.0.0.1", server.port, CODE, "Kitchen", device.cert_der)
    assert (await task).name == "Kitchen"


async def test_pairing_stops_after_max_attempts(tmp_path):
    server = _server(["111111", "222222"], max_attempts=2)
    task = await _start(server)
    device = FakeDevice(tmp_path)
    for _ in range(2):
        with pytest.raises(PairingFailed):
            await pair_as_device("127.0.0.1", server.port, CODE, "Kitchen", device.cert_der)
    assert await task is None


async def test_refusing_on_the_pc_fails_the_attempt(tmp_path):
    server = _server([None], max_attempts=1)
    task = await _start(server)
    with pytest.raises(PairingFailed, match="refused"):
        await pair_as_device(
            "127.0.0.1", server.port, CODE, "Kitchen", FakeDevice(tmp_path).cert_der
        )
    assert await task is None


async def test_hanging_up_after_the_pc_reply_still_spends_an_attempt(tmp_path):
    """Regression: a peer that took the PC's tag and left was not counted as a guess."""
    server = _server(["111111"], max_attempts=1)
    task = await _start(server)
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    from halecho.cpace import CPace
    from halecho.pairing import CI

    sid = bytes(16)
    own = CPace(b"999999", CI, sid, b"cert")
    writer.write(
        frames.encode_json(
            {
                "type": "pair_hello",
                "v": 1,
                "sid": sid.hex(),
                "name": "x",
                "cert": "00",
                "y": own.message.hex(),
            }
        )
    )
    await writer.drain()
    assert (await frames.read_frame(reader)).json()["type"] == "pair_reply"
    writer.close()
    assert await task is None
