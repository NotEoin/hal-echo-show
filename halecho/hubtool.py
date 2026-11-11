"""One-shot worker for hal-hub's `exec` manifest (`halecho/hal-module.toml`).

python -m halecho.hubtool FUNCTION    JSON arguments on stdin, one JSON value on stdout

The hub runs every tool in this checkout's own environment, and this package imports
nothing from Hal. A failure exits non-zero with the reason on stderr; stdout stays empty.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from . import tools

FUNCTIONS: dict[str, Callable[..., Any]] = {"say": tools.say, "devices": tools.devices}
USAGE_EXIT = 2
FAILED_EXIT = 1


def run(name: str, raw_args: str) -> str:
    """Runs one call and returns its JSON result; raises on a bad name or arguments."""
    if name not in FUNCTIONS:
        raise KeyError(f"no function {name!r}; known: {', '.join(sorted(FUNCTIONS))}")
    args = json.loads(raw_args or "{}")
    if not isinstance(args, dict):
        raise ValueError("arguments must be a JSON object")
    return json.dumps(FUNCTIONS[name](**args))


def main(argv: list[str] | None = None) -> int:
    """Entry point: reads the arguments from stdin, prints the result."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return USAGE_EXIT
    try:
        out = run(argv[0], sys.stdin.read())
    except (KeyError, ValueError, TypeError) as exc:
        print(f"hubtool: {exc}", file=sys.stderr)
        return USAGE_EXIT
    except RuntimeError as exc:
        print(f"hubtool: {exc}", file=sys.stderr)
        return FAILED_EXIT
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
