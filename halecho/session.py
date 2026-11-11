"""One connected device: its messages, its brain and its turns.

The device does the listening (wake word, recording, Whisper) and the playing; the PC does
the thinking and the voice. A turn, as the device sees it:

    device: wake {turn, score}       -> pc: floor {turn, granted}
    device: utterance {turn, text}   -> pc: state thinking, then per sentence
                                        say {turn, seq, text, sr} + AUDIO frames + say_end
                                     -> pc: turn_end {turn, finished}
    device: barge_in {turn}          -> the brain's turn is cancelled

Turn ids come from the device; turns the PC starts itself (`hal-echo say`) set the top bit.
Brains are blocking iterators, so each turn runs on the session's single worker thread and
sends its frames back through the event loop. `docs/dev/protocol.md` lists every message.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import logging
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import frames, models, screens
from .backend import Backend, Brain
from .floor import Floor
from .registry import Device

log = logging.getLogger(__name__)

LINK_VERSION = 1
PC_TURN_BIT = 0x8000_0000
AUDIO_CHUNK_S = 0.25  # frames this long keep a barge-in prompt without flooding the link
SEND_TIMEOUT_S = 30.0  # a send from the turn thread waits at most this for the event loop
APPROVAL_SLACK_S = 5.0  # the device's own listening limit runs first; this covers the link
SENTENCE_ENDERS = ".!?\n"
MIN_SENTENCE_CHARS = 2  # "Mr." alone is not a sentence boundary worth a breath

TOO_LONG = "That took too long."
MONITOR_OPEN = "Here is the hardware monitor."
MONITOR_NOT_HERE = "The hardware monitor is not available in this room."
UNAVAILABLE = "My brain is not available."


def sentences(deltas: Iterable[str]) -> Iterator[str]:
    """Turns a stream of text deltas into whole sentences, as soon as each one ends."""
    buf = ""
    for delta in deltas:
        buf += delta
        while True:
            cut = next(
                (
                    i + 1
                    for i, ch in enumerate(buf)
                    if ch in SENTENCE_ENDERS and i >= MIN_SENTENCE_CHARS
                ),
                -1,
            )
            if cut == -1:
                break
            sentence, buf = buf[:cut].strip(), buf[cut:]
            if sentence:
                yield sentence
    if buf.strip():
        yield buf.strip()


class SessionClosed(Exception):
    """The device disconnected while a turn was still sending to it."""


@dataclass
class _Turn:
    id: int
    cancelled: threading.Event = field(default_factory=threading.Event)


class DeviceSession:
    """Serves one paired device over an established TLS connection."""

    def __init__(
        self,
        device: Device,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        backend: Backend,
        settings: Any,
        floor: Floor,
        server_name: str,
    ) -> None:
        self.device = device
        self.reader = reader
        self.writer = writer
        self.backend = backend
        self.settings = settings
        self.floor = floor
        self.server_name = server_name
        self.muted = False
        self.awake = False
        self._loop = asyncio.get_running_loop()
        self._write_lock = asyncio.Lock()
        self._worker = concurrent.futures.ThreadPoolExecutor(1, f"turns-{device.id}")
        self._brain: Brain | None = None
        self._turn: _Turn | None = None
        self._approval: concurrent.futures.Future[str] | None = None
        self._approval_turn = 0
        self._audio: dict[int, bytearray] = {}
        self._next_pc_turn = 0
        self._next_transfer = 0
        self.closed = asyncio.Event()
        self._screen: screens.TerminalScreen | None = None
        self._next_term = 0
        self._gone = threading.Event()  # `closed`, readable from the turn thread

    # -- sending -----------------------------------------------------------------
    async def send(self, msg: dict[str, Any]) -> None:
        """Writes one JSON message."""
        await self.send_raw(frames.encode_json(msg))

    async def send_raw(self, data: bytes) -> None:
        """Writes one encoded frame; frames from different tasks never interleave."""
        async with self._write_lock:
            self.writer.write(data)
            await self.writer.drain()

    def _send_from_thread(self, data: bytes) -> None:
        """Sends from the turn thread; raises `SessionClosed` once the device has gone."""
        if self._gone.is_set():
            raise SessionClosed
        coro = self.send_raw(data)
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except RuntimeError as exc:  # the event loop has already closed
            coro.close()
            raise SessionClosed from exc
        try:
            future.result(SEND_TIMEOUT_S)
        except (
            ConnectionError,
            concurrent.futures.TimeoutError,
            concurrent.futures.CancelledError,
        ) as exc:
            raise SessionClosed from exc

    # -- receiving ---------------------------------------------------------------
    async def run(self) -> None:
        """Handles the device's messages until it disconnects."""
        try:
            while True:
                frame = await frames.read_frame(self.reader)
                if frame.kind == frames.AUDIO:
                    turn, _seq, pcm = frame.audio()
                    if turn in self._audio:
                        self._audio[turn] += pcm
                    continue
                if frame.kind == frames.TERM:
                    term, data = frame.term()
                    if self._screen is not None and self._screen.term == term:
                        self._screen.input(data)
                    continue
                await self._dispatch(frame.json())
        except (asyncio.IncompleteReadError, ConnectionError):
            # A device going away (power cut, Wi-Fi drop) is normal; it reconnects on its own
            log.info("%s disconnected", self.device.name)
        finally:
            self._gone.set()
            self.closed.set()
            await self._close()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        kind = msg["type"]
        handler = {
            "hello": self._on_hello,
            "wake": self._on_wake,
            "utterance": self._on_utterance,
            "utterance_audio": self._on_utterance_audio,
            "utterance_audio_end": self._on_utterance_audio_end,
            "approval": self._on_approval,
            "barge_in": self._on_barge_in,
            "state": self._on_state,
            "need_model": self._on_need_model,
            "update_result": self._on_update_result,
            "ping": self._on_ping,
            "term_size": self._on_term_size,
            "term_close": self._on_term_close,
            "crash_report": self._on_crash_report,
        }.get(kind)
        if handler is None:
            log.warning("%s sent an unknown message '%s'", self.device.name, kind)
            return
        await handler(msg)

    async def _on_hello(self, msg: dict[str, Any]) -> None:
        log.info(
            "%s connected: app %s, %s",
            self.device.name,
            msg.get("app_version"),
            msg.get("abi"),
        )
        self.muted = bool(msg.get("muted"))
        listener = self.settings.get("listener")
        await self.send(
            {
                "type": "welcome",
                "v": LINK_VERSION,
                "server_name": self.server_name,
                "device_name": self.device.name,
                "mode": self.device.mode,
                "listener": listener,
                "models": {
                    name: {
                        "kind": models.get(name).kind,
                        "sha256": models.get(name).sha256,
                        "size": models.get(name).size,
                    }
                    for name in (listener["stt_model"], listener["wake_model"])
                },
            }
        )

    async def _on_wake(self, msg: dict[str, Any]) -> None:
        turn = int(msg["turn"])
        granted = await self.floor.request(self.device.id, float(msg.get("score", 0.0)))
        await self.send({"type": "floor", "turn": turn, "granted": granted})

    async def _on_utterance(self, msg: dict[str, Any]) -> None:
        await self._heard(int(msg["turn"]), str(msg.get("text", "")), bool(msg.get("followup")))

    async def _on_utterance_audio(self, msg: dict[str, Any]) -> None:
        self._audio[int(msg["turn"])] = bytearray()

    async def _on_utterance_audio_end(self, msg: dict[str, Any]) -> None:
        turn = int(msg["turn"])
        pcm = bytes(self._audio.pop(turn, b""))
        text = await asyncio.to_thread(self.backend.transcribe, pcm)
        if self._approval is not None and turn == self._approval_turn:
            self._approval.set_result(text)
            return
        await self._heard(turn, text, bool(msg.get("followup")))

    async def _on_approval(self, msg: dict[str, Any]) -> None:
        if self._approval is not None and not self._approval.done():
            self._approval.set_result(str(msg.get("text", "")))

    async def _on_barge_in(self, msg: dict[str, Any]) -> None:
        turn = self._turn
        if turn is not None and turn.id == int(msg["turn"]):
            log.info("%s: barge-in", self.device.name)
            turn.cancelled.set()
            if self._brain is not None and hasattr(self._brain, "cancel"):
                await asyncio.to_thread(self._brain.cancel)

    async def _on_state(self, msg: dict[str, Any]) -> None:
        self.muted = bool(msg.get("muted", self.muted))
        self.awake = bool(msg.get("awake", self.awake))
        if not self.awake:
            await self._close_screen("the room went quiet")

    async def _on_term_size(self, msg: dict[str, Any]) -> None:
        if self._screen is not None and self._screen.term == int(msg.get("term", -1)):
            self._screen.resize(int(msg["cols"]), int(msg["rows"]))

    async def _on_term_close(self, msg: dict[str, Any]) -> None:
        if self._screen is not None and self._screen.term == int(msg.get("term", -1)):
            await self._close_screen("closed on the device")

    async def _on_need_model(self, msg: dict[str, Any]) -> None:
        name = str(msg.get("name", ""))
        try:
            model, path = await asyncio.to_thread(models.ensure, name)
        except models.ModelError as exc:
            log.error("%s asked for a model: %s", self.device.name, exc)
            await self.send({"type": "error", "about": "need_model", "message": str(exc)})
            return
        await self.send_file(path, "model", model.name, model.sha256)

    async def _on_update_result(self, msg: dict[str, Any]) -> None:
        log.info("%s update: %s", self.device.name, msg.get("message") or msg.get("ok"))

    async def _on_crash_report(self, msg: dict[str, Any]) -> None:
        log.error("%s crashed earlier:\n%s", self.device.name, str(msg.get("text", ""))[:8000])

    async def _on_ping(self, msg: dict[str, Any]) -> None:
        await self.send({"type": "pong", "t": msg.get("t")})

    # -- turns -------------------------------------------------------------------
    async def _heard(self, turn_id: int, text: str, followup: bool) -> None:
        if self._approval is not None and not self._approval.done():
            self._approval.set_result(text)  # an answer recorded as an utterance still counts
            return
        # A follow-up needs no name, but people still say it: it is removed either way
        named, request = self.backend.addressed(text)
        if not named and not followup:
            log.info("%s heard, not addressed: %r", self.device.name, text)
            await self.send({"type": "turn_end", "turn": turn_id, "heard": False})
            return
        if not request:
            # "Hal" alone: the next utterance is the request
            await self.send({"type": "listen", "turn": turn_id, "purpose": "request"})
            return
        command = screens.match(request)
        if command is not None:
            await self._screen_command(turn_id, command)
            return
        self._start_turn(turn_id, request)

    # -- screens -------------------------------------------------------------------
    async def _screen_command(self, turn_id: int, command: str) -> None:
        if command == screens.CLOSE_SCREEN:
            await self._close_screen("asked to close")
            await self.send({"type": "turn_end", "turn": turn_id, "finished": True})
            return
        if not screens.allowed(self.settings, self.device.mode):
            self._say_on_turn(turn_id, MONITOR_NOT_HERE)
            return
        if self._screen is None or self._screen.closed.is_set():
            self._next_term += 1
            self._screen = screens.TerminalScreen(
                self._next_term,
                list(self.settings.get("screens.monitor.command")),
                str(self.settings.get("screens.monitor.title")),
                self.send,
                self.send_raw,
                float(self.settings.get("screens.monitor.timeout_s")),
            )
            await self._screen.open()
        self._say_on_turn(turn_id, MONITOR_OPEN)

    async def _close_screen(self, reason: str, notify: bool = True) -> None:
        screen, self._screen = self._screen, None
        if screen is not None:
            await screen.close(reason, notify)

    def _say_on_turn(self, turn_id: int, line: str) -> None:
        """Speaks a fixed line as the reply to the device's own turn."""
        turn = _Turn(turn_id)
        self._worker.submit(self._speak_turn, turn, [line])

    def _start_turn(self, turn_id: int, request: str) -> None:
        if self._turn is not None:
            self._turn.cancelled.set()  # a new request replaces one still being answered
        turn = _Turn(turn_id)
        self._turn = turn
        self._worker.submit(self._run_turn, turn, request)

    def say(self, text: str) -> int:
        """Speaks `text` on this device as a turn of its own; returns the turn id."""
        self._next_pc_turn += 1
        turn = _Turn(PC_TURN_BIT | self._next_pc_turn)
        self._worker.submit(self._speak_turn, turn, [text])
        return turn.id

    def _run_turn(self, turn: _Turn, request: str) -> None:
        log.info("%s: you: %s", self.device.name, request)
        # Home mode's stub brain uses no GPU, so it does not wait for gpu-light to make room
        claims_gpu = self.device.mode != "home"
        if claims_gpu:
            self.backend.turn_started()
        try:
            self._send_from_thread(frames.encode_json({"type": "state", "state": "thinking"}))
            try:
                brain = self._ensure_brain()
            except Exception as exc:  # noqa: BLE001 - any brain failure is spoken, then logged
                log.error("%s: brain unavailable: %s", self.device.name, exc)
                self._speak(turn, [UNAVAILABLE])
                return
            replies = _with_notices(brain.ask(request), self.backend.timeout_errors)
            self._speak(turn, sentences(replies))
        except SessionClosed:
            log.info("%s: disconnected during a turn", self.device.name)
        finally:
            if claims_gpu:
                self.backend.turn_ended()
            if self._turn is turn:
                self._turn = None

    def _speak_turn(self, turn: _Turn, lines: list[str]) -> None:
        self._turn = turn
        try:
            self._speak(turn, lines)
        except SessionClosed:
            log.info("%s: disconnected while speaking", self.device.name)
        finally:
            if self._turn is turn:
                self._turn = None

    def _speak(self, turn: _Turn, lines: Iterable[str]) -> None:
        seq = 0
        try:
            for sentence in lines:
                if turn.cancelled.is_set():
                    break
                log.info("%s: HAL: %s", self.device.name, sentence)
                for pcm, sr in self.backend.synth(sentence):
                    if turn.cancelled.is_set():
                        break
                    seq += 1
                    self._send_segment(turn.id, seq, sentence, pcm, sr)
        except SessionClosed:
            raise
        except Exception as exc:  # noqa: BLE001 - a failed reply is logged; the session carries on
            log.error("%s: reply failed: %s", self.device.name, exc)
        finished = not turn.cancelled.is_set()
        self._send_from_thread(
            frames.encode_json({"type": "turn_end", "turn": turn.id, "finished": finished})
        )

    def _send_segment(self, turn_id: int, seq: int, text: str, pcm: bytes, sr: int) -> None:
        self._send_from_thread(
            frames.encode_json({"type": "say", "turn": turn_id, "seq": seq, "text": text, "sr": sr})
        )
        step = max(2, int(sr * AUDIO_CHUNK_S) * 2)
        for part, start in enumerate(range(0, len(pcm), step)):
            self._send_from_thread(frames.encode_audio(turn_id, part, pcm[start : start + step]))
        self._send_from_thread(frames.encode_json({"type": "say_end", "turn": turn_id, "seq": seq}))

    def _ensure_brain(self) -> Brain:
        if self._brain is None:
            self._brain = self.backend.make_brain(self.device.mode, self._listen, self.settings)
        return self._brain

    def _listen(self) -> str:
        """Asks the device to hear one spoken approval; returns it, or "" on silence."""
        turn = self._turn
        if turn is None:
            return ""
        limit = float(self.settings.get("listener.approval_listen_s", 20))
        self._approval = concurrent.futures.Future()
        self._approval_turn = turn.id
        try:
            self._send_from_thread(
                frames.encode_json(
                    {"type": "listen", "turn": turn.id, "purpose": "approval", "timeout_s": limit}
                )
            )
            return self._approval.result(timeout=limit + APPROVAL_SLACK_S)
        except (SessionClosed, concurrent.futures.TimeoutError):
            return ""  # no answer is a refusal
        finally:
            self._approval = None

    # -- files ---------------------------------------------------------------------
    async def send_file(
        self, path: Path, purpose: str, name: str, sha256: str | None = None
    ) -> None:
        """Sends a model or an app update as BLOB frames, with its size and SHA-256."""
        digest = sha256 or await asyncio.to_thread(models.file_sha256, path)
        self._next_transfer += 1
        transfer = self._next_transfer
        size = path.stat().st_size
        chunk = int(self.settings.get("updates.chunk_kib", 256)) * 1024
        await self.send(
            {
                "type": "blob_begin",
                "id": transfer,
                "purpose": purpose,
                "name": name,
                "size": size,
                "sha256": digest,
            }
        )
        sent = hashlib.sha256()
        with path.open("rb") as fh:
            while data := fh.read(chunk):
                sent.update(data)
                await self.send_raw(frames.encode_blob(transfer, data))
        if sent.hexdigest() != digest:
            log.error("%s changed while it was sent", path)
        await self.send({"type": "blob_end", "id": transfer})

    async def _close(self) -> None:
        await self._close_screen("the device disconnected", notify=False)
        if self._turn is not None:
            self._turn.cancelled.set()
        if self._approval is not None and not self._approval.done():
            self._approval.set_result("")
        brain, self._brain = self._brain, None
        self._worker.shutdown(wait=False, cancel_futures=True)
        if brain is not None and hasattr(brain, "close"):
            await asyncio.to_thread(brain.close)
        self.writer.close()


def _with_notices(
    deltas: Iterator[str], timeout_errors: tuple[type[Exception], ...]
) -> Iterator[str]:
    """The reply, with a timeout or a mid-turn failure turned into a spoken notice."""
    try:
        yield from deltas
    except timeout_errors as exc:
        log.warning("brain: %s", exc)
        yield f" {TOO_LONG}"
    except Exception as exc:  # noqa: BLE001 - any brain failure mid-turn is spoken, then logged
        log.error("brain failed: %s", exc)
        yield f" {UNAVAILABLE}"
