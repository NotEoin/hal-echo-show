"""The brain of `home` mode: a stub until Home Assistant is wired in.

It answers every request with a fixed sentence, so a device in a shared room never reaches
the user's own tools, files or accounts. `home_assistant.url` and `home_assistant.token_file`
are read and checked so the settings are in place for the real integration; it is not built
yet, and nothing is sent to Home Assistant.
"""

from __future__ import annotations

import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

NOT_SET_UP = "Home Assistant is not connected yet, so there is nothing I can do from this room."
NOT_BUILT = (
    "Home Assistant is configured, but this version cannot talk to it yet, "
    "so there is nothing I can do from this room."
)


class HomeAssistantBrain:
    """Answers with a fixed sentence that says what is missing."""

    def __init__(self, settings: Any) -> None:
        self.url = settings.get("home_assistant.url")
        token_file = settings.get("home_assistant.token_file")
        self.token_problem = check_token_file(Path(token_file)) if token_file else None

    def ask(self, text: str) -> Iterator[str]:
        """Yields the fixed answer; `text` is not sent anywhere."""
        yield NOT_BUILT if self.url and not self.token_problem else NOT_SET_UP

    def cancel(self) -> None:
        """Nothing runs between sentences, so there is nothing to stop."""

    def close(self) -> None:
        """Holds no connections."""


def check_token_file(path: Path) -> str | None:
    """None when `path` is a token file only its owner can read, else what is wrong."""
    if not path.is_file():
        return f"{path} does not exist"
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        return f"{path} is readable by other users: chmod 600 it"
    return None
