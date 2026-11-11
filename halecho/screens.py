"""Screen commands the bridge answers itself, before the brain: the hardware monitor.

"Hey Hal, open the hardware monitor" shows btop, running on this PC, in a terminal on the
device that heard it; "close the monitor" brings the eye back. Matching is a fixed set of
phrases, so the screen opens at once, with no model round trip and no tool approval.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from . import frames
from .terminal import PtyProcess, TerminalError

log = logging.getLogger(__name__)

OPEN_MONITOR = "open_monitor"
CLOSE_SCREEN = "close_screen"

_MONITOR = r"(?:hardware|system|resource|performance|computer|pc)\s+monitor"
# "can you", "could you" and "please" in front are politeness, not part of the command
_POLITE = r"^(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
_OPEN = re.compile(
    rf"{_POLITE}(?:open(?:\s+up)?|show(?:\s+me)?|start|launch|bring\s+up|pull\s+up|display|put\s+up)"
    rf"\s+(?:the\s+|a\s+|your\s+|my\s+)?{_MONITOR}(?:\s+please)?$",
    re.I,
)
_CLOSE = re.compile(
    rf"{_POLITE}(?:close|hide|exit|quit|stop|dismiss|turn\s+off|put\s+away)"
    rf"\s+(?:the\s+|your\s+|my\s+)?(?:{_MONITOR}|monitor)(?:\s+please)?$"
    r"|^(?:go\s+)?back\s+to\s+(?:the\s+|your\s+)?eye$",
    re.I,
)


def match(request: str) -> str | None:
    """`OPEN_MONITOR`, `CLOSE_SCREEN`, or None when the request is for the brain."""
    text = re.sub(r"[^\w\s]", " ", request).strip()
    text = re.sub(r"\s+", " ", text)
    if _OPEN.match(text):
        return OPEN_MONITOR
    if _CLOSE.match(text):
        return CLOSE_SCREEN
    return None


def allowed(settings: Any, mode: str) -> bool:
    """Whether a device in `mode` may show the hardware monitor."""
    return mode in (settings.get("screens.monitor.modes") or [])


SIZE_WAIT_S = 5.0  # the device reports its terminal size at once; this covers an old app
DEFAULT_SIZE = (80, 24)


class TerminalScreen:
    """One terminal screen on a device, from `open` to `close`.

    The program starts when the device reports its terminal size, so it draws at the right size
    from its first frame. Output goes out as `TERM` frames in order; the screen closes on
    request, when the program exits, or after `timeout_s`.
    """

    def __init__(
        self,
        term: int,
        argv: list[str],
        title: str,
        send_json: Callable[[dict[str, Any]], Awaitable[None]],
        send_raw: Callable[[bytes], Awaitable[None]],
        timeout_s: float,
    ) -> None:
        self.term = term
        self.title = title
        self._send_json = send_json
        self._send_raw = send_raw
        self._timeout_s = timeout_s
        self._proc = PtyProcess(argv, self._output, self._exited)
        self._tasks: set[asyncio.Task] = set()
        self._timers: list[asyncio.TimerHandle] = []
        self._started = False
        self.closed = asyncio.Event()

    async def open(self) -> None:
        """Tells the device to show the terminal, and arms the timers."""
        loop = asyncio.get_running_loop()
        await self._send_json(
            {"type": "view", "name": "terminal", "term": self.term, "title": self.title}
        )
        self._timers.append(loop.call_later(SIZE_WAIT_S, self._start_if_unsized))
        self._timers.append(loop.call_later(self._timeout_s, self._spawn_close, "timed out"))

    def resize(self, cols: int, rows: int) -> None:
        """Starts the program at this size, or resizes it if it runs already."""
        if self.closed.is_set():
            return
        cols, rows = max(cols, 1), max(rows, 1)
        if self._started:
            self._proc.resize(cols, rows)
            return
        self._started = True
        try:
            self._proc.start(cols, rows)
        except TerminalError as exc:
            log.error("%s", exc)
            self._spawn_close(str(exc))

    def _start_if_unsized(self) -> None:
        # Only a start: resizing a program that the device already sized shrank it to 80 x 24
        if not self._started:
            self.resize(*DEFAULT_SIZE)

    def input(self, data: bytes) -> None:
        """Keys and mouse reports from the device, for the program."""
        self._proc.write(data)

    async def close(self, reason: str, notify: bool = True) -> None:
        """Ends the program and, when `notify`, puts the eye back on the device."""
        if self.closed.is_set():
            return
        self.closed.set()
        log.info("terminal %d closed: %s", self.term, reason)
        for timer in self._timers:
            timer.cancel()
        await self._proc.close()
        if notify:
            with contextlib.suppress(ConnectionError, RuntimeError):
                await self._send_json({"type": "view", "name": "eye", "term": self.term})

    def _output(self, data: bytes) -> None:
        for start in range(0, len(data), frames.MAX_PAYLOAD - frames.BLOB_HEADER.size):
            chunk = data[start : start + frames.MAX_PAYLOAD - frames.BLOB_HEADER.size]
            self._track(self._send_raw(frames.encode_term(self.term, chunk)))

    def _exited(self) -> None:
        self._spawn_close("the program exited")

    def _spawn_close(self, reason: str) -> None:
        self._track(self.close(reason))

    def _track(self, coro: Awaitable[None]) -> None:
        # The loop keeps only weak references to tasks; these must finish
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
