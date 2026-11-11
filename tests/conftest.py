"""Shared fixtures: private config, state and cache directories, and a fake backend."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from halecho import config


@pytest.fixture(autouse=True)
def private_dirs(tmp_path, monkeypatch):
    """Keeps every test away from the real ~/.config, ~/.cache and runtime directory."""
    for env, name in (
        ("HAL_ECHO_CONFIG_DIR", "config"),
        ("HAL_ECHO_STATE_DIR", "state"),
        ("HAL_ECHO_CACHE_DIR", "cache"),
    ):
        monkeypatch.setenv(env, str(tmp_path / name))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    (tmp_path / "run").mkdir()
    return tmp_path


class FakeBrain:
    """Replies with fixed text; can ask for an approval mid-turn."""

    def __init__(self, reply: str, listen: Callable[[], str], ask_approval: bool) -> None:
        self.reply = reply
        self.listen = listen
        self.ask_approval = ask_approval
        self.asked: list[str] = []
        self.approvals: list[str] = []
        self.cancelled = threading.Event()
        self.closed = False

    def ask(self, text: str) -> Iterator[str]:
        self.asked.append(text)
        if self.ask_approval:
            self.approvals.append(self.listen())
        for word in self.reply.split(" "):
            if self.cancelled.is_set():
                return
            yield word + " "

    def cancel(self) -> None:
        self.cancelled.set()

    def close(self) -> None:
        self.closed = True


class FakeBackend:
    """A backend with no hal-voice: words become a tone, "Hal ..." is addressed."""

    timeout_errors: tuple[type[Exception], ...] = (TimeoutError,)

    def __init__(self, reply: str = "Good afternoon. I am fine.", ask_approval: bool = False):
        self.reply = reply
        self.ask_approval = ask_approval
        self.brains: list[FakeBrain] = []
        self.modes: list[str] = []
        self.turns = 0

    def make_brain(self, mode: str, listen: Callable[[], str], settings: Any) -> FakeBrain:
        self.modes.append(mode)
        brain = FakeBrain(self.reply, listen, self.ask_approval)
        self.brains.append(brain)
        return brain

    def synth(self, sentence: str) -> Iterator[tuple[bytes, int]]:
        yield b"\x01\x00" * 1600 * len(sentence.split()), 16000

    def addressed(self, text: str) -> tuple[bool, str]:
        words = text.strip(" ,.!?").split(" ", 1)
        if words[0].lower().strip(",") != "hal":
            return False, text.strip(" ,.!?")  # as hal-voice's addressed() does
        return True, words[1].strip(" ,.!?") if len(words) > 1 else ""

    def transcribe(self, pcm: bytes) -> str:
        return f"Hal, {len(pcm)} bytes"

    def turn_started(self) -> None:
        self.turns += 1

    def turn_ended(self) -> None:
        pass


@pytest.fixture
def settings() -> config.Cfg:
    """The packaged defaults, bound to localhost and free ports, without mDNS."""
    cfg = config.load()
    cfg["server"].update({"host": "127.0.0.1", "port": 0, "pair_port": 0, "advertise": False})
    return cfg
