"""The speech-model catalogue (`models.toml`) and its download cache.

Devices never reach the internet for models: they ask the PC, which downloads each file
once, checks its size and SHA-256 against the catalogue, and sends it over the paired link.
"""

from __future__ import annotations

import hashlib
import logging
import tomllib
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT_S = 60  # per socket read, not for the whole file
CHUNK_BYTES = 1 << 20


class ModelError(RuntimeError):
    """An unknown model name, or a download that failed or did not match its hash."""


@dataclass(frozen=True)
class Model:
    """One catalogue entry."""

    name: str
    kind: str
    url: str
    size: int
    sha256: str


def catalogue() -> dict[str, Model]:
    """Every model in `models.toml`, by name."""
    text = resources.files("halecho").joinpath("models.toml").read_text(encoding="utf-8")
    return {name: Model(name=name, **entry) for name, entry in tomllib.loads(text).items()}


def get(name: str) -> Model:
    """The catalogue entry for `name`.

    Raises:
        ModelError: there is no such model.
    """
    models = catalogue()
    if name not in models:
        raise ModelError(f"unknown model '{name}'; known: {', '.join(sorted(models))}")
    return models[name]


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def cached_path(model: Model) -> Path:
    """Where the model lives in the cache, downloaded or not."""
    return config.cache_dir() / "models" / Path(model.url).name


def ensure(name: str) -> tuple[Model, Path]:
    """The model and its cached file, downloading and checking it first if needed.

    Raises:
        ModelError: the download failed, or the file's size or hash is wrong.
    """
    model = get(name)
    path = cached_path(model)
    if path.exists() and path.stat().st_size == model.size:
        return model, path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    log.info("downloading %s (%.0f MB)", model.name, model.size / 1e6)
    digest = hashlib.sha256()
    try:
        # the URLs are the fixed https ones in models.toml
        with urllib.request.urlopen(model.url, timeout=DOWNLOAD_TIMEOUT_S) as resp:  # noqa: S310 - catalogue URLs only
            with partial.open("wb") as fh:
                while chunk := resp.read(CHUNK_BYTES):
                    digest.update(chunk)
                    fh.write(chunk)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise ModelError(f"downloading {model.name} failed: {exc}") from exc
    if partial.stat().st_size != model.size or digest.hexdigest() != model.sha256:
        partial.unlink(missing_ok=True)
        raise ModelError(f"{model.name} does not match its catalogue size and SHA-256")
    partial.replace(path)
    return model, path
