"""What the bridge takes from hal-voice: the brains, the HAL voice, GPU sharing and Whisper.

hal-voice is imported only here, and only when `serve` starts, so the rest of the package
(pairing, the protocol, the tests) works without it. `Backend` is the seam the tests fake.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any, Protocol

PCM_MAX = 32767


class BackendUnavailable(RuntimeError):
    """hal-voice is not installed in this environment, or its brain cannot start."""


class Brain(Protocol):
    """hal-voice's brain interface: streams the reply to one turn as text deltas."""

    def ask(self, text: str) -> Iterator[str]:
        """Streams the reply to `text`."""
        ...

    def cancel(self) -> None:
        """Stops the turn in progress."""
        ...

    def close(self) -> None:
        """Releases the brain's processes."""
        ...


class Backend(Protocol):
    """Everything the bridge needs that is not about the link."""

    #: The exceptions a brain raises when a turn runs out of time.
    timeout_errors: tuple[type[Exception], ...]

    def make_brain(self, mode: str, listen: Callable[[], str], settings: Any) -> Brain:
        """A brain for one device in `mode`; `listen` hears one spoken approval."""
        ...

    def synth(self, sentence: str) -> Iterator[tuple[bytes, int]]:
        """The sentence in HAL's voice, as (16-bit mono PCM, sample rate) segments."""
        ...

    def addressed(self, text: str) -> tuple[bool, str]:
        """Whether HAL was named in `text`, and the request with the name removed."""
        ...

    def transcribe(self, pcm: bytes) -> str:
        """The text of 16 kHz 16-bit mono PCM, for devices with `stt_location: pc`."""
        ...

    def turn_started(self) -> None:
        """A turn is starting: ask gpu-light to make room for the brain."""
        ...

    def turn_ended(self) -> None:
        """A turn ended: give the room back after hal-voice's linger time."""
        ...


class HalVoiceBackend:
    """The real backend, built on an installed hal-voice."""

    def __init__(self) -> None:
        try:
            from halvoice import config as hv_config
            from halvoice import tts
            from halvoice.brains import TurnTimeout
            from halvoice.gpu import VoiceClaims
            from halvoice.handsfree import addressed
        except ImportError as exc:
            raise BackendUnavailable(
                f"hal-voice is not installed here ({exc}); see the README's install steps"
            ) from exc
        self.timeout_errors: tuple[type[Exception], ...] = (TurnTimeout,)
        self._hv_cfg = hv_config.load()
        self._tts = tts
        self._addressed = addressed
        self._claims = VoiceClaims.from_config(self._hv_cfg)
        self._claims.start_service()
        # GPT-SoVITS synthesises one request at a time; two rooms speaking share it in turn
        self._synth_lock = threading.Lock()
        self._turn_wait_s = float(self._hv_cfg.get("gpu.turn_wait_s", 12))
        self._transcriber: Any = None

    def make_brain(self, mode: str, listen: Callable[[], str], settings: Any) -> Brain:
        """A brain for `mode`, built by `halecho.modes`."""
        from . import modes

        return modes.make_brain(mode, self._hv_cfg, listen, settings)

    def synth(self, sentence: str) -> Iterator[tuple[bytes, int]]:
        """Synthesises with hal-voice's GPT-SoVITS client and FX chain."""
        import numpy as np

        with self._synth_lock:
            segments = list(self._tts.synth_stream(sentence))
        for audio, sr in segments:
            pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * PCM_MAX
            yield pcm.astype("<i2").tobytes(), int(sr)

    def addressed(self, text: str) -> tuple[bool, str]:
        """hal-voice's own test for "Hal, ..." and "..., Hal"."""
        return self._addressed(text)

    def transcribe(self, pcm: bytes) -> str:
        """Transcribes with hal-voice's faster-whisper, loaded on first use."""
        import numpy as np
        from halvoice.stt import Transcriber

        if self._transcriber is None:
            self._transcriber = Transcriber()
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / PCM_MAX
        return self._transcriber.transcribe(audio)

    def turn_started(self) -> None:
        """Claims GPU room for the brain, waiting at most `gpu.turn_wait_s`."""
        self._claims.turn_started()
        self._claims.wait_for_turn(self._turn_wait_s)

    def turn_ended(self) -> None:
        """Releases the turn's GPU claim."""
        self._claims.turn_ended()

    def close(self) -> None:
        """Closes the connection to gpu-light, giving back any room still held."""
        self._claims.close()
