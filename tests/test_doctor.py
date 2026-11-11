"""`hal-echo doctor`: each check reports a status and a fix."""

from __future__ import annotations

import socket

from halecho import doctor
from halecho.identity import load_or_create


def _by_label(settings) -> dict[str, tuple[str, str]]:
    return {label: (status, detail) for label, status, detail in doctor.results(settings)}


def test_fresh_install_warns_but_does_not_fail_on_identity_and_devices(settings):
    settings["server"]["port"] = 47899
    checks = _by_label(settings)
    assert checks["identity"][0] == doctor.WARN
    assert checks["devices"] == (doctor.WARN, "none paired")
    assert checks["bridge"] == (doctor.WARN, "not running")


def test_identity_is_ok_once_created(settings):
    load_or_create()
    assert _by_label(settings)["identity"][0] == doctor.OK


def test_port_in_use_fails(settings):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        settings["server"]["port"] = busy.getsockname()[1]
        assert _by_label(settings)["port"][0] == doctor.FAIL


def test_firewall_that_is_off_is_reported(tmp_path, monkeypatch):
    """Regression: doctor reported ufw as present while it was disabled and enforced nothing."""
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/sbin/ufw")
    conf = tmp_path / "ufw.conf"
    conf.write_text("ENABLED=no\nLOGLEVEL=low\n")
    assert doctor.check_firewall(conf)[1] == doctor.WARN
    conf.write_text("ENABLED=yes\n")
    assert doctor.check_firewall(conf)[1] == doctor.OK


def test_run_exits_1_when_a_check_fails(settings, capsys, monkeypatch):
    monkeypatch.setattr(doctor, "check_hal_voice", lambda: ("hal-voice", doctor.FAIL, "missing"))
    settings["server"]["port"] = 47899
    assert doctor.run(settings) == 1
    assert "[FAIL] hal-voice: missing" in capsys.readouterr().out
