"""Floor control: one answer per wake word, however many devices heard it."""

from __future__ import annotations

import asyncio

from halecho.floor import Floor


async def test_loudest_device_in_one_window_wins():
    floor = Floor(0.05)
    results = await asyncio.gather(
        floor.request("hall", 0.3), floor.request("kitchen", 0.8), floor.request("study", 0.5)
    )
    assert results == [False, True, False]


async def test_tie_goes_to_the_first_report():
    floor = Floor(0.05)
    assert await asyncio.gather(floor.request("a", 0.5), floor.request("b", 0.5)) == [True, False]


async def test_reports_in_separate_windows_each_win():
    floor = Floor(0.02)
    assert await floor.request("bedroom", 0.1)
    assert await floor.request("kitchen", 0.1)
