"""The speaker EQ: lows the Echo cannot play are cut, presence is lifted, peaks never clip.

Skipped when pedalboard (a hal-voice dependency) is not installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pedalboard")
np = pytest.importorskip("numpy")

from halecho import config, speaker_eq  # noqa: E402 - only after the skip checks

SR = 32000  # GPT-SoVITS's output rate


def _gain_db(freq_hz: float) -> float:
    t = np.arange(SR) / SR
    tone = (0.1 * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
    out = speaker_eq.apply(speaker_eq.chain(config.load()), tone, SR)
    middle = slice(SR // 4, 3 * SR // 4)  # past the filters' settling time
    return 20 * np.log10(np.sqrt(np.mean(out[middle] ** 2)) / np.sqrt(np.mean(tone[middle] ** 2)))


def test_lows_the_speaker_cannot_play_are_cut():
    assert _gain_db(60) < -10


def test_presence_is_lifted():
    assert _gain_db(3500) > 3


def test_mid_voice_is_left_close_to_level():
    assert abs(_gain_db(1000)) < 1.5


def test_loud_input_is_limited_below_full_scale():
    t = np.arange(SR) / SR
    loud = np.sin(2 * np.pi * 3500 * t).astype(np.float32) * 0.99
    out = speaker_eq.apply(speaker_eq.chain(config.load()), loud, SR)
    assert np.max(np.abs(out)) <= 1.0


def test_disabled_eq_passes_audio_through():
    cfg = config.load()
    cfg["speaker_eq"]["enabled"] = False
    audio = np.ones(10, dtype=np.float32) * 0.5
    assert speaker_eq.apply(speaker_eq.chain(cfg), audio, SR) is audio
