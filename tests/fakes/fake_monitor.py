"""A stand-in for btop: reports its terminal size on start and on SIGWINCH, echoes input."""

import os
import signal
import sys


def report(*_):
    cols, rows = os.get_terminal_size(1)
    sys.stdout.write(f"SIZE {cols}x{rows}\n")
    sys.stdout.flush()


signal.signal(signal.SIGWINCH, report)
report()
for line in sys.stdin:
    sys.stdout.write("GOT " + line)
    sys.stdout.flush()
