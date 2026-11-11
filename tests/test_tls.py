"""The pinned TLS context and the hints around it: discovery and the hal-voice seam."""

from __future__ import annotations

import ipaddress
import ssl

import pytest

from halecho import backend, discovery, tls
from halecho.identity import load_or_create, self_signed
from halecho.registry import Registry


def test_server_context_requires_tls_1_3_and_a_client_certificate():
    ctx = tls.server_context(load_or_create(), [])
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3
    assert ctx.verify_mode == ssl.CERT_REQUIRED


class _Peer:
    def __init__(self, der: bytes | None) -> None:
        self.der = der

    def getpeercert(self, binary_form: bool) -> bytes | None:
        return self.der


def test_pinned_device_finds_the_paired_certificate():
    der = self_signed("d")[1]
    dev = Registry().add("Kitchen", "home", der)
    assert tls.pinned_device(_Peer(der), Registry()) == dev


@pytest.mark.parametrize("der", [None, b"not paired"])
def test_pinned_device_refuses_a_missing_or_unknown_certificate(der):
    with pytest.raises(ssl.SSLError):
        tls.pinned_device(_Peer(der), Registry())


def test_lan_address_is_an_ipv4_address():
    assert ipaddress.ip_address(discovery.lan_address()).version == 4


def test_announcement_carries_a_fingerprint_hint_not_the_whole_fingerprint():
    ann = discovery.Announcer("pc", 47800, "ab" * 32, pairing=False, pair_port=47801)
    assert ann.info.properties[b"fp"] == b"ab" * 8
    assert ann.info.port == 47800
    assert discovery.Announcer("pc", 47800, "ab" * 32, True, 47801).info.port == 47801


def test_backend_without_hal_voice_names_the_fix(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "halvoice", None)
    with pytest.raises(backend.BackendUnavailable, match="README"):
        backend.HalVoiceBackend()
