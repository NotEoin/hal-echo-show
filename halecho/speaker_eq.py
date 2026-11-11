"""EQ for the device's speaker, applied to HAL's voice after hal-voice's own FX chain.

The Echo Show 5 has one small driver. Below about 150 Hz it cannot move air, so a deep voice's
lowest energy only blurs the low mids, and the voice sounds muffled. This chain removes what the
driver cannot play, trims the boxy low mids, lifts presence and air, and scales a sentence down
when the boosts would clip it. A per-sentence scale, not a limiter: pedalboard's limiter adds
make-up gain, and a sentence is short enough that one gain does not pump. The defaults in
`speaker_eq` are a starting point, tuned by ear on one device.

pedalboard comes with hal-voice; this module is imported only by `halecho.backend`.
"""

from __future__ import annotations

from typing import Any

import numpy as np

PEAK_CEILING = 0.89  # -1 dBFS: headroom below full scale after the boosts


def chain(settings: Any) -> Any | None:
    """The pedalboard chain from `speaker_eq`, or None when it is off."""
    if not settings.get("speaker_eq.enabled"):
        return None
    from pedalboard import HighpassFilter, HighShelfFilter, PeakFilter, Pedalboard

    get = settings.get
    highpass = float(get("speaker_eq.highpass_hz"))
    return Pedalboard(
        [
            # Each is first order (6 dB per octave); two make a 12 dB per octave cut
            HighpassFilter(cutoff_frequency_hz=highpass),
            HighpassFilter(cutoff_frequency_hz=highpass),
            PeakFilter(
                cutoff_frequency_hz=float(get("speaker_eq.mud_hz")),
                gain_db=float(get("speaker_eq.mud_gain_db")),
                q=1.0,
            ),
            PeakFilter(
                cutoff_frequency_hz=float(get("speaker_eq.presence_hz")),
                gain_db=float(get("speaker_eq.presence_gain_db")),
                q=0.9,
            ),
            HighShelfFilter(
                cutoff_frequency_hz=float(get("speaker_eq.air_hz")),
                gain_db=float(get("speaker_eq.air_gain_db")),
            ),
        ]
    )


def apply(board: Any | None, audio: np.ndarray, sr: int) -> np.ndarray:
    """`audio` (float32 mono) through `board`; unchanged when `board` is None."""
    if board is None or audio.size == 0:
        return audio
    out = board(audio.astype(np.float32)[np.newaxis, :], sr, reset=True)[0]
    peak = float(np.max(np.abs(out)))
    return out * (PEAK_CEILING / peak) if peak > PEAK_CEILING else out
