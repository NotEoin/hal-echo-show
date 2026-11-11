"""TLS 1.3 with both certificates pinned: the encryption and authentication of the link.

The server trusts exactly the certificates in the registry. Each paired device's self-signed
certificate is loaded as its own trust anchor (`VERIFY_X509_PARTIAL_CHAIN` lets a leaf be
one), so OpenSSL refuses any other client during the handshake; `pinned_device` then
checks the fingerprint again against the registry before a session starts.
"""

from __future__ import annotations

import ssl

from .identity import Identity, der_to_pem, fingerprint
from .registry import Device, Registry


def server_context(identity: Identity, devices: list[Device]) -> ssl.SSLContext:
    """A TLS 1.3 server context that requires a client certificate from `devices`."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(identity.cert_path, identity.key_path)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    if devices:
        ctx.load_verify_locations(cadata="".join(der_to_pem(d.cert_der).decode() for d in devices))
    return ctx


def pinned_device(ssl_object: ssl.SSLObject | ssl.SSLSocket, registry: Registry) -> Device:
    """The paired device at the other end of a completed handshake.

    Raises:
        ssl.SSLError: the peer sent no certificate, or one that is not paired.
    """
    der = ssl_object.getpeercert(binary_form=True)
    if not der:
        raise ssl.SSLError("the device sent no certificate")
    dev = registry.by_fingerprint(fingerprint(der))
    if dev is None:
        raise ssl.SSLError("the device's certificate is not paired")
    return dev
