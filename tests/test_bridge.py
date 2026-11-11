"""The bridge end to end: pinned TLS, turns, approvals, barge-in, models and control."""

from __future__ import annotations

import asyncio
import hashlib
import ssl
import sys
from pathlib import Path

import pytest

from halecho import frames, models
from halecho.identity import load_or_create
from halecho.registry import Registry
from halecho.server import Bridge, control_request
from halecho.session import PC_TURN_BIT

from conftest import FakeBackend
from fakedevice import FakeDevice


@pytest.fixture
async def bridge(settings):
    backend = FakeBackend()
    bridge = Bridge(settings, load_or_create(), Registry(), backend)
    ready = asyncio.Event()
    task = asyncio.create_task(bridge.serve(ready))
    await ready.wait()
    yield bridge
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _paired(bridge: Bridge, tmp_path, mode: str = "desk") -> FakeDevice:
    device = FakeDevice(tmp_path / "device")
    Registry().add(device.name, mode, device.cert_der)
    await device.connect(bridge.port, bridge.identity.cert_der)
    await device.send({"type": "hello", "app_version": "test", "abi": "arm64-v8a"})
    return device


async def test_unpaired_certificate_is_refused(bridge, tmp_path):
    device = FakeDevice(tmp_path / "stranger")
    with pytest.raises((ssl.SSLError, ConnectionError, asyncio.IncompleteReadError)):
        await device.connect(bridge.port, bridge.identity.cert_der)
        await device.send({"type": "hello"})
        await device.frame()


async def test_device_refuses_a_pc_with_another_certificate(bridge, tmp_path):
    device = FakeDevice(tmp_path / "device")
    Registry().add(device.name, "desk", device.cert_der)
    impostor = FakeDevice(tmp_path / "impostor")
    with pytest.raises(ssl.SSLError):
        await device.connect(bridge.port, impostor.cert_der)


async def test_welcome_carries_mode_and_listener_settings(bridge, tmp_path):
    device = await _paired(bridge, tmp_path, mode="personal")
    welcome = await device.expect("welcome")
    assert welcome["mode"] == "personal"
    assert welcome["listener"]["awake_s"] == 300
    stt = welcome["listener"]["stt_model"]
    assert welcome["models"][stt]["sha256"] == models.get(stt).sha256


async def test_addressed_request_is_answered_sentence_by_sentence(bridge, tmp_path):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 7, "text": "Hal, how are you?"})
    assert (await device.expect("state"))["state"] == "thinking"
    first = await device.expect("say")
    second = await device.expect("say")
    end = await device.expect("turn_end")
    assert (first["text"], second["text"]) == ("Good afternoon.", "I am fine.")
    assert end == {"type": "turn_end", "turn": 7, "finished": True}
    assert bridge.backend.brains[0].asked == ["how are you"]
    assert all(turn == 7 for turn, _, _ in device.audio)


async def test_speech_not_addressed_to_hal_ends_the_turn_unheard(bridge, tmp_path):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 1, "text": "pass the salt"})
    assert await device.expect("turn_end") == {"type": "turn_end", "turn": 1, "heard": False}
    assert bridge.backend.brains == []


async def test_follow_up_needs_no_name(bridge, tmp_path):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 2, "text": "and tomorrow?", "followup": True})
    await device.expect("turn_end")
    assert bridge.backend.brains[0].asked == ["and tomorrow"]


async def test_name_alone_asks_the_device_for_the_request(bridge, tmp_path):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 3, "text": "Hal."})
    assert await device.expect("listen") == {"type": "listen", "turn": 3, "purpose": "request"}


async def test_spoken_approval_reaches_the_brain(bridge, tmp_path):
    bridge.backend.ask_approval = True
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 4, "text": "Hal, delete my notes"})
    listen = await device.expect("listen")
    assert listen["purpose"] == "approval" and listen["timeout_s"] == 20
    await device.send({"type": "approval", "turn": 4, "text": "yes"})
    await device.expect("turn_end")
    assert bridge.backend.brains[0].approvals == ["yes"]


async def test_barge_in_cancels_the_reply(bridge, tmp_path):
    bridge.backend.reply = " ".join(f"Sentence {n}." for n in range(50))
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 5, "text": "Hal, talk"})
    await device.expect("say")
    await device.send({"type": "barge_in", "turn": 5})
    end = await device.expect("turn_end")
    assert end["finished"] is False
    assert bridge.backend.brains[0].cancelled.is_set()


async def test_audio_utterance_is_transcribed_on_the_pc(bridge, tmp_path):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance_audio", "turn": 6})
    await device.send_raw(frames.encode_audio(6, 0, b"\x00" * 3200))
    await device.send({"type": "utterance_audio_end", "turn": 6})
    await device.expect("turn_end")
    assert bridge.backend.brains[0].asked == ["3200 bytes"]


async def test_two_devices_hearing_one_wake_word_get_one_answer(bridge, tmp_path):
    near = await _paired(bridge, tmp_path)
    far = FakeDevice(tmp_path / "far", name="Hall")
    Registry().add(far.name, "home", far.cert_der)
    await far.connect(bridge.port, bridge.identity.cert_der)
    await far.send({"type": "hello"})
    await near.expect("welcome")
    await far.expect("welcome")
    await near.send({"type": "wake", "turn": 1, "score": 0.9})
    await far.send({"type": "wake", "turn": 1, "score": 0.4})
    assert (await near.expect("floor"))["granted"] is True
    assert (await far.expect("floor"))["granted"] is False


async def test_requested_model_is_sent_with_its_hash(bridge, tmp_path, monkeypatch):
    blob = tmp_path / "model.bin"
    blob.write_bytes(b"weights" * 100_000)
    digest = hashlib.sha256(blob.read_bytes()).hexdigest()
    model = models.Model(
        "tiny", "whisper", "https://example.invalid/m", blob.stat().st_size, digest
    )
    monkeypatch.setattr(models, "ensure", lambda name: (model, blob))
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "need_model", "name": "tiny"})
    begin = await device.expect("blob_begin")
    received = bytearray()
    while True:
        frame = await device.frame()
        if frame.kind == frames.BLOB:
            received += frame.blob()[1]
            continue
        assert frame.json() == {"type": "blob_end", "id": begin["id"]}
        break
    assert begin["purpose"] == "model" and begin["sha256"] == digest
    assert hashlib.sha256(received).hexdigest() == digest


async def test_say_through_the_control_socket_uses_a_pc_turn(bridge, tmp_path):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    reply = await control_request({"cmd": "say", "text": "Dinner is ready."})
    assert reply["ok"] and reply["devices"] == ["Kitchen"]
    say = await device.expect("say")
    assert say["turn"] & PC_TURN_BIT and say["text"] == "Dinner is ready."


async def test_unpaired_device_cannot_reconnect(bridge, tmp_path):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.close()
    Registry().remove(device.name)
    with pytest.raises((ssl.SSLError, ConnectionError, asyncio.IncompleteReadError)):
        await device.connect(bridge.port, bridge.identity.cert_der)
        await device.send({"type": "hello"})
        await device.frame()


async def test_home_mode_does_not_wait_for_gpu_room(bridge, tmp_path):
    """Regression: a home-mode turn waited for gpu-light although its stub uses no GPU."""
    device = await _paired(bridge, tmp_path, mode="home")
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 1, "text": "Hal, lights"})
    await device.expect("turn_end")
    assert bridge.backend.turns == 0


FAKE_MONITOR = [sys.executable, str(Path(__file__).parent / "fakes" / "fake_monitor.py")]


async def _term_output(device: FakeDevice, marker: bytes, timeout: float = 5.0) -> bytes:
    seen = b""
    while marker not in seen:
        frame = await device.frame(timeout)
        if frame.kind == frames.TERM:
            seen += frame.term()[1]
    return seen


async def test_hardware_monitor_opens_streams_takes_input_and_closes(bridge, tmp_path):
    bridge.settings["screens"]["monitor"]["command"] = FAKE_MONITOR
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 1, "text": "Hal, open the hardware monitor"})
    view = await device.expect("view")
    assert view["name"] == "terminal" and view["title"] == "Hardware monitor"
    await device.send({"type": "term_size", "term": view["term"], "cols": 96, "rows": 26})
    assert b"SIZE 96x26" in await _term_output(device, b"SIZE 96x26")
    await device.send_raw(frames.encode_term(view["term"], b"tap\n"))
    await _term_output(device, b"GOT tap")
    screen = bridge.sessions[next(iter(bridge.sessions))]._screen
    await device.send({"type": "utterance", "turn": 2, "text": "Hal, close the monitor"})
    closed = await device.expect("view")
    assert closed == {"type": "view", "name": "eye", "term": view["term"]}
    assert not screen._proc.running


async def test_monitor_is_refused_in_home_mode(bridge, tmp_path):
    device = await _paired(bridge, tmp_path, mode="home")
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 1, "text": "Hal, open the hardware monitor"})
    say = await device.expect("say")
    assert "not available" in say["text"]


async def test_monitor_closes_when_the_room_goes_quiet(bridge, tmp_path):
    bridge.settings["screens"]["monitor"]["command"] = FAKE_MONITOR
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 1, "text": "Hal, show the system monitor"})
    view = await device.expect("view")
    await device.send({"type": "term_size", "term": view["term"], "cols": 80, "rows": 24})
    await _term_output(device, b"SIZE 80x24")
    await device.send({"type": "state", "awake": False, "muted": False})
    assert (await device.expect("view"))["name"] == "eye"


async def test_disconnect_ends_the_monitor_program(bridge, tmp_path):
    bridge.settings["screens"]["monitor"]["command"] = FAKE_MONITOR
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "utterance", "turn": 1, "text": "Hal, open the hardware monitor"})
    view = await device.expect("view")
    await device.send({"type": "term_size", "term": view["term"], "cols": 80, "rows": 24})
    await _term_output(device, b"SIZE 80x24")
    screen = bridge.sessions[next(iter(bridge.sessions))]._screen
    await device.close()
    await asyncio.wait_for(screen.closed.wait(), 5)
    assert not screen._proc.running


async def test_crash_report_is_logged(bridge, tmp_path, caplog):
    device = await _paired(bridge, tmp_path)
    await device.expect("welcome")
    await device.send({"type": "crash_report", "text": "java.lang.IllegalStateException: boom"})
    await device.send({"type": "ping", "t": 1})
    await device.expect("pong")
    assert "IllegalStateException: boom" in caplog.text
