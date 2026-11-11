"""Paired devices and settings: names, modes, file permissions and unknown keys."""

from __future__ import annotations

import stat

import pytest

from halecho import config
from halecho.identity import load_or_create, self_signed
from halecho.registry import Registry, RegistryError, clean_name


def _cert() -> bytes:
    return self_signed("device")[1]


def test_device_is_found_by_name_or_id():
    reg = Registry()
    dev = reg.add("Kitchen", "home", _cert())
    assert reg.find("kitchen") == dev
    assert reg.find(dev.id) == dev
    with pytest.raises(RegistryError):
        reg.find("garage")


def test_names_are_made_unique():
    reg = Registry()
    reg.add("Echo", "desk", _cert())
    assert reg.add("Echo", "desk", _cert()).name == "Echo 2"


def test_repairing_one_certificate_replaces_its_entry():
    reg, cert = Registry(), _cert()
    reg.add("Echo", "desk", cert)
    reg.add("Desk", "personal", cert)
    assert [(d.name, d.mode) for d in reg.all()] == [("Desk", "personal")]


def test_unknown_mode_is_refused():
    with pytest.raises(RegistryError):
        Registry().add("Echo", "garden", _cert())


def test_names_are_printable_ascii():
    assert clean_name("Kitchen\u2014\n Echo") == "Kitchen Echo"
    assert clean_name("\x00") == "Echo Show"


def test_registry_and_key_are_owner_only():
    reg = Registry()
    reg.add("Echo", "desk", _cert())
    ident = load_or_create()
    for path in (reg.path, ident.key_path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(reg.path.parent.stat().st_mode) == 0o700


def test_identity_is_stable_across_loads():
    assert load_or_create().fingerprint == load_or_create().fingerprint


def test_user_settings_override_defaults():
    config.private_dir(config.config_dir())
    config.user_file().write_text("listener:\n  awake_s: 60\n")
    cfg = config.load()
    assert cfg.get("listener.awake_s") == 60
    assert cfg.get("listener.followup_s") == 8


def test_unknown_setting_is_an_error():
    config.private_dir(config.config_dir())
    config.user_file().write_text("listener:\n  awake_secs: 60\n")
    with pytest.raises(config.ConfigError, match=r"listener\.awake_secs"):
        config.load()
