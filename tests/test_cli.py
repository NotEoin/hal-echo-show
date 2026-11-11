"""`hal-echo` commands that work without a running bridge."""

from __future__ import annotations

import pytest

from halecho import cli
from halecho.identity import self_signed
from halecho.registry import Registry


@pytest.fixture
def kitchen():
    return Registry().add("Kitchen", "home", self_signed("d")[1])


def test_devices_lists_paired_devices_with_unknown_state(kitchen, capsys):
    assert cli.main(["devices"]) == 0
    out = capsys.readouterr().out
    assert "Kitchen" in out and "home" in out and "not running" in out


def test_mode_rename_and_unpair(kitchen, capsys):
    assert cli.main(["mode", "kitchen", "personal"]) == 0
    assert Registry().find("Kitchen").mode == "personal"
    assert cli.main(["rename", "Kitchen", "Study"]) == 0
    assert cli.main(["unpair", "Study"]) == 0
    assert Registry().all() == []


def test_unknown_device_is_an_error(capsys):
    assert cli.main(["unpair", "Garage"]) == 1
    assert "no paired device" in capsys.readouterr().err


def test_bad_mode_is_refused_by_the_parser():
    with pytest.raises(SystemExit):
        cli.main(["mode", "Kitchen", "garden"])


def test_firewall_prints_rules_for_the_given_address_only(capsys):
    assert cli.main(["firewall", "--address", "192.168.1.50"]) == 0
    out = capsys.readouterr().out
    assert "sudo ufw allow from 192.168.1.50 to any port 47800 proto tcp" in out
    assert "port 47801" in out


def test_firewall_without_addresses_says_what_to_pass(capsys):
    assert cli.main(["firewall"]) == 1
    assert "--address" in capsys.readouterr().out


def test_say_without_the_bridge_names_the_fix(capsys):
    assert cli.main(["say", "hello"]) == 1
    assert "hal-echo serve" in capsys.readouterr().err
