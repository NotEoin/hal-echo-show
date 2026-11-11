"""The model catalogue and the checked download."""

from __future__ import annotations

import hashlib
import io
import urllib.request

import pytest

from halecho import config, models


def test_catalogue_entries_are_https_with_sha256():
    for model in models.catalogue().values():
        assert model.url.startswith("https://")
        assert len(model.sha256) == 64 and int(model.sha256, 16) >= 0
        assert model.kind in ("whisper", "vosk")


def test_configured_models_are_in_the_catalogue():
    cfg = config.load()
    models.get(cfg.get("listener.stt_model"))
    models.get(cfg.get("listener.wake_model"))


def _fake_download(monkeypatch, body: bytes, model: models.Model) -> None:
    monkeypatch.setattr(models, "get", lambda name: model)
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: io.BytesIO(body))


def test_download_is_kept_when_size_and_hash_match(monkeypatch):
    body = b"weights"
    model = models.Model(
        "m", "whisper", "https://x.test/m.bin", len(body), hashlib.sha256(body).hexdigest()
    )
    _fake_download(monkeypatch, body, model)
    _, path = models.ensure("m")
    assert path.read_bytes() == body


def test_download_with_the_wrong_hash_is_discarded(monkeypatch):
    model = models.Model("m", "whisper", "https://x.test/m.bin", 7, "0" * 64)
    _fake_download(monkeypatch, b"weights", model)
    with pytest.raises(models.ModelError):
        models.ensure("m")
    assert not models.cached_path(model).exists()
    assert not models.cached_path(model).with_suffix(".bin.part").exists()
