"""Personal mode against hal-voice's real ACP brain: desktop tools are refused unspoken.

Skipped when hal-voice is not installed in the test environment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("halvoice")

from halvoice import config as hv_config

from halecho import config, modes

FAKE = Path(__file__).parent / "fakes" / "fake_hal_acp.py"


@pytest.fixture
def brain_for(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    log = tmp_path / "answers.log"
    asked: list[str] = []

    def listen() -> str:
        asked.append("asked")
        return "yes"

    def make(mode: str):
        cfg = hv_config.load(force=True)
        cfg["brain"]["mode"] = "hal"
        cfg["brain"]["hal_command"] = [sys.executable, str(FAKE), str(log)]
        return modes.make_brain(mode, cfg, listen, config.load())

    def answers() -> list[dict]:
        return [json.loads(x) for x in log.read_text().splitlines()]

    return make, asked, answers


def test_personal_mode_refuses_a_desktop_tool_without_asking(brain_for):
    make, asked, answers = brain_for
    brain = make("personal")
    try:
        assert "".join(brain.ask("desktop_type [act] desktop")) == "Done."
    finally:
        brain.close()
    assert asked == []
    assert answers() == [{"outcome": {"outcome": "cancelled"}}]


def test_personal_mode_asks_for_other_packs(brain_for):
    make, asked, answers = brain_for
    brain = make("personal")
    try:
        "".join(brain.ask("calendar_add [write] calendar"))
    finally:
        brain.close()
    assert asked == ["asked"]
    assert answers()[0]["outcome"]["optionId"] == "allow-1"


def test_desk_mode_asks_for_desktop_tools(brain_for):
    make, asked, _answers = brain_for
    brain = make("desk")
    try:
        "".join(brain.ask("desktop_type [act] desktop"))
    finally:
        brain.close()
    assert asked == ["asked"]
