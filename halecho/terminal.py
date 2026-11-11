"""A program in a pseudo-terminal, for the screens the device shows (`halecho.screens`).

The program runs under `setsid -c` so the terminal is its controlling one: resizing the
terminal then sends it SIGWINCH, as a real terminal window would. Output is read on the event
loop with `add_reader`, so a quiet program costs nothing. The environment asks for colour and
UTF-8, because btop refuses to draw without a UTF-8 locale.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import pty
import shutil
import signal
import struct
import subprocess
import termios
from collections.abc import Callable

log = logging.getLogger(__name__)

READ_BYTES = 65536
STOP_TIMEOUT_S = 3.0  # a program gets this long after SIGTERM before SIGKILL
WINSIZE = struct.Struct("HHHH")  # rows, columns, pixel width, pixel height
TERMINAL_ENV = {
    "TERM": "xterm-256color",
    "COLORTERM": "truecolor",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}


class TerminalError(RuntimeError):
    """The program could not be started."""


class PtyProcess:
    """One program in its own pseudo-terminal, until it exits or is closed.

    Args:
        argv: the program and its arguments.
        on_output: called on the event loop with each chunk the program writes.
        on_exit: called once on the event loop when the program has gone.
    """

    def __init__(
        self,
        argv: list[str],
        on_output: Callable[[bytes], None],
        on_exit: Callable[[], None],
    ) -> None:
        self.argv = argv
        self.on_output = on_output
        self.on_exit = on_exit
        self._master = -1
        self._proc: subprocess.Popen | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ended = False

    def start(self, cols: int, rows: int) -> None:
        """Starts the program in a terminal of `cols` x `rows`.

        Raises:
            TerminalError: the program or `setsid` is not installed.
        """
        setsid = shutil.which("setsid")
        program = shutil.which(self.argv[0])
        if setsid is None or program is None:
            raise TerminalError(f"cannot start {self.argv[0]}: not installed")
        master, slave = pty.openpty()
        _set_size(master, cols, rows)
        try:
            self._proc = subprocess.Popen(
                [setsid, "-c", program, *self.argv[1:]],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env={**os.environ, **TERMINAL_ENV},
                close_fds=True,
            )
        finally:
            os.close(slave)
        os.set_blocking(master, False)
        self._master = master
        self._loop = asyncio.get_running_loop()
        self._loop.add_reader(master, self._readable)
        log.info("started %s (%dx%d)", self.argv[0], cols, rows)

    @property
    def running(self) -> bool:
        """True from `start` until the program has gone."""
        return self._master >= 0 and not self._ended

    def resize(self, cols: int, rows: int) -> None:
        """Gives the terminal a new size; the program redraws on SIGWINCH."""
        if self.running:
            _set_size(self._master, cols, rows)

    def write(self, data: bytes) -> None:
        """Sends keys and mouse reports to the program; dropped if it cannot take them now."""
        if not self.running:
            return
        with contextlib.suppress(BlockingIOError, OSError):
            os.write(self._master, data)

    def _readable(self) -> None:
        try:
            data = os.read(self._master, READ_BYTES)
        except BlockingIOError:
            return
        except OSError:
            data = b""  # EIO: the program has closed its end of the terminal
        if data:
            self.on_output(data)
            return
        self._finish()

    def _finish(self) -> None:
        if self._ended:
            return
        self._ended = True
        if self._loop is not None and self._master >= 0:
            self._loop.remove_reader(self._master)
        self.on_exit()

    async def close(self) -> None:
        """Ends the program: SIGTERM to its session, SIGKILL if it lingers."""
        proc = self._proc
        self._finish()
        if self._master >= 0:
            with contextlib.suppress(OSError):
                os.close(self._master)
            self._master = -1
        if proc is None or proc.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            await asyncio.to_thread(proc.wait, STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            log.warning("%s ignored SIGTERM; killing it", self.argv[0])
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            await asyncio.to_thread(proc.wait, STOP_TIMEOUT_S)


def _set_size(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, WINSIZE.pack(rows, cols, 0, 0))
