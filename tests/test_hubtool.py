"""The Hal pack: the manifest's shape and the one-shot worker."""

from __future__ import annotations

import io
import tomllib
from pathlib import Path

import pytest

from halecho import hubtool, tools
from halecho.identity import self_signed
from halecho.registry import Registry

MANIFEST = Path(__file__).parents[1] / "halecho" / "hal-module.toml"
# the schema 2 keys hal-hub accepts, as hal-voice's tests list them
TOP_KEYS = {"schema", "module", "tools", "install", "units", "desktop"}


def test_manifest_is_schema_2_exec_through_hubtool():
    m = tomllib.loads(MANIFEST.read_text())
    assert m["schema"] == 2 and set(m) <= TOP_KEYS
    assert m["module"]["exec"][1:] == ["-m", "halecho.hubtool"]
    assert {t["function"] for t in m["tools"]} == set(hubtool.FUNCTIONS)


def test_unknown_function_is_a_usage_error(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert hubtool.main(["nope"]) == hubtool.USAGE_EXIT
    assert "no function" in capsys.readouterr().err


def test_say_without_the_bridge_fails_with_the_fix(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"text": "hello"}'))
    assert hubtool.main(["say"]) == hubtool.FAILED_EXIT
    assert "hal-echo serve" in capsys.readouterr().err


def test_say_refuses_empty_text():
    with pytest.raises(ValueError):
        tools.say("   ")


def test_devices_lists_paired_devices_offline_without_the_bridge():
    Registry().add("Kitchen", "home", self_signed("d")[1])
    assert tools.devices() == [{"name": "Kitchen", "mode": "home", "connected": False}]
