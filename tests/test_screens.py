"""Screen commands and the terminal they run in."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from halecho import screens
from halecho.terminal import PtyProcess, TerminalError

FAKE_MONITOR = [sys.executable, str(Path(__file__).parent / "fakes" / "fake_monitor.py")]


@pytest.mark.parametrize(
    "request_text",
    [
        "open the hardware monitor",
        "Show me the system monitor.",
        "bring up the hardware monitor please",
        "launch my PC monitor",
        "open up the hardware monitor, please",  # heard on the device, 2026-11-11
        "can you open the hardware monitor",
    ],
)
def test_open_phrases_open_the_monitor(request_text):
    assert screens.match(request_text) == screens.OPEN_MONITOR


@pytest.mark.parametrize(
    "request_text", ["close the monitor", "hide the hardware monitor", "back to the eye"]
)
def test_close_phrases_close_the_screen(request_text):
    assert screens.match(request_text) == screens.CLOSE_SCREEN


@pytest.mark.parametrize(
    "request_text",
    [
        "open the garage",
        "how hot is the GPU on the hardware monitor",
        "what does the hardware monitor show",
        "monitor my sleep",
    ],
)
def test_other_requests_go_to_the_brain(request_text):
    assert screens.match(request_text) is None


def test_monitor_is_not_allowed_in_home_mode(settings):
    assert screens.allowed(settings, "desk")
    assert not screens.allowed(settings, "home")


async def _collect(out: list[bytes], marker: bytes, timeout: float = 5.0) -> None:
    async def wait() -> None:
        while marker not in b"".join(out):
            await asyncio.sleep(0.02)

    await asyncio.wait_for(wait(), timeout)


async def test_program_sees_its_size_and_its_resizes():
    out: list[bytes] = []
    exited = asyncio.Event()
    proc = PtyProcess(FAKE_MONITOR, out.append, exited.set)
    proc.start(100, 30)
    await _collect(out, b"SIZE 100x30")
    proc.resize(120, 40)
    await _collect(out, b"SIZE 120x40")
    proc.write(b"hello\n")
    await _collect(out, b"GOT hello")
    await proc.close()
    assert exited.is_set() and not proc.running


async def test_missing_program_is_reported():
    proc = PtyProcess(["no-such-program-hal-echo"], lambda _: None, lambda: None)
    with pytest.raises(TerminalError, match="not installed"):
        proc.start(80, 24)
