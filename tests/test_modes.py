"""Mode rules that do not need hal-voice: denied packs, the Home Assistant stub, sentences."""

from __future__ import annotations

import pytest

from halecho import config
from halecho.homeassistant import NOT_BUILT, NOT_SET_UP, HomeAssistantBrain, check_token_file
from halecho.modes import denied_pack
from halecho.session import sentences

DENIED = frozenset({"desktop"})


def _request(title: str) -> dict:
    return {"toolCall": {"title": title}}


def test_desktop_pack_request_is_denied():
    assert denied_pack(_request("desktop_screenshot [read] desktop"), DENIED) == "desktop"


def test_other_packs_are_not_denied():
    assert denied_pack(_request("calendar_add [write] calendar"), DENIED) is None


def test_unexpected_title_is_left_to_hal_voice():
    assert denied_pack(_request("Allow desktop_type?"), DENIED) is None


def test_home_mode_answers_that_it_is_not_set_up():
    brain = HomeAssistantBrain(config.load())
    assert list(brain.ask("turn on the lights")) == [NOT_SET_UP]


def test_home_mode_with_a_url_and_private_token_says_it_is_not_built(tmp_path):
    token = tmp_path / "token"
    token.write_text("x")
    token.chmod(0o600)
    cfg = config.load()
    cfg["home_assistant"].update({"url": "http://ha.test:8123", "token_file": str(token)})
    assert list(HomeAssistantBrain(cfg).ask("lights")) == [NOT_BUILT]


def test_token_file_readable_by_others_is_reported(tmp_path):
    token = tmp_path / "token"
    token.write_text("x")
    token.chmod(0o644)
    assert "chmod 600" in (check_token_file(token) or "")


@pytest.mark.parametrize(
    ("deltas", "expected"),
    [
        (["Hello", ", Dave. How", " are you?"], ["Hello, Dave.", "How are you?"]),
        (["No ending"], ["No ending"]),
        (["A", ". B."], ["A. B."]),  # a stop this early is not a sentence end
        ([], []),
    ],
)
def test_sentences_end_as_soon_as_they_are_complete(deltas, expected):
    assert list(sentences(deltas)) == expected
