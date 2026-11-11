"""Settings and file locations.

The packaged `config.yaml` holds every key with its default. The user file
(`~/.config/hal-echo-show/config.yaml`) may set only keys that exist there, so a typo fails
loudly instead of being ignored. `HAL_ECHO_CONFIG_DIR`, `HAL_ECHO_STATE_DIR` and
`HAL_ECHO_CACHE_DIR` move the three directories, which the tests rely on.
"""

from __future__ import annotations

import copy
import os
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

APP = "hal-echo-show"


class ConfigError(ValueError):
    """The user's settings file is malformed or sets a key that does not exist."""


def _xdg(env: str, xdg: str, fallback: str) -> Path:
    override = os.environ.get(env)
    if override:
        return Path(override)
    return Path(os.environ.get(xdg) or Path.home() / fallback) / APP


def config_dir() -> Path:
    """Settings, the PC's identity and the paired devices."""
    return _xdg("HAL_ECHO_CONFIG_DIR", "XDG_CONFIG_HOME", ".config")


def state_dir() -> Path:
    """The control socket's fallback location and other run-time state."""
    return _xdg("HAL_ECHO_STATE_DIR", "XDG_STATE_HOME", ".local/state")


def cache_dir() -> Path:
    """Downloaded speech models, sent to devices on request."""
    return _xdg("HAL_ECHO_CACHE_DIR", "XDG_CACHE_HOME", ".cache")


def private_dir(path: Path) -> Path:
    """Creates `path` if needed and makes it readable by the owner only."""
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


class Cfg(dict):
    """A settings tree read with dotted paths: `cfg.get("server.port")`."""

    def get(self, dotted: str, default: Any = None) -> Any:  # type: ignore[override]  # a dotted path where dict.get takes a key, on purpose
        node: Any = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def defaults() -> dict:
    """The packaged defaults."""
    text = resources.files("halecho").joinpath("config.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _merge(base: dict, over: dict, prefix: str = "") -> None:
    for key, value in over.items():
        path = f"{prefix}{key}"
        if key not in base:
            raise ConfigError(f"unknown setting '{path}' in {user_file()}")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ConfigError(f"'{path}' must be a mapping in {user_file()}")
            _merge(base[key], value, f"{path}.")
        else:
            base[key] = value


def user_file() -> Path:
    """The user's settings file; it need not exist."""
    return config_dir() / "config.yaml"


def load() -> Cfg:
    """The defaults with the user's settings laid over them.

    Raises:
        ConfigError: the user file is not a YAML mapping or sets an unknown key.
    """
    cfg = copy.deepcopy(defaults())
    path = user_file()
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path} must hold a YAML mapping")
        _merge(cfg, data)
    return Cfg(cfg)
