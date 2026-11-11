"""Who answers when several devices hear one "Hey Hal".

A device reports its wake as soon as it hears the name, with a score (its detector's
confidence weighted by how loud the name was). The first report opens a contest of
`floor.window_ms`; when it closes, the highest score gets the floor and the rest go back
to listening. Devices whose reports are further apart are in different rooms, or speaking
to different people, and each gets its own turn.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class _Contest:
    entries: dict[str, float] = field(default_factory=dict)
    winner: asyncio.Future[str] = field(
        default_factory=lambda: asyncio.get_running_loop().create_future()
    )


class Floor:
    """Groups wake reports that arrive within one window and picks one device to answer."""

    def __init__(self, window_s: float) -> None:
        self.window_s = window_s
        self._open: _Contest | None = None

    async def request(self, device_id: str, score: float) -> bool:
        """True when `device_id` should answer; waits out the rest of the window."""
        contest = self._open
        if contest is None:
            contest = self._open = _Contest()
            asyncio.get_running_loop().call_later(self.window_s, self._close, contest)
        contest.entries[device_id] = max(score, contest.entries.get(device_id, score))
        return await asyncio.shield(contest.winner) == device_id

    def _close(self, contest: _Contest) -> None:
        if self._open is contest:
            self._open = None
        # ties go to the device that reported first, which dict order preserves
        winner = max(contest.entries, key=lambda d: contest.entries[d])
        if not contest.winner.done():
            contest.winner.set_result(winner)
