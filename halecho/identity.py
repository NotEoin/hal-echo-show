"""The PC's long-term TLS identity: an ECDSA P-256 key and a self-signed certificate.

Devices pin the certificate's SHA-256 fingerprint at pairing, so no certificate authority is
involved and the certificate's names and dates carry no trust. P-256 because Android 11's TLS
stack and Android Keystore both support it; Ed25519 certificates they do not.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from . import config

KEY_FILE = "pc-key.pem"
CERT_FILE = "pc-cert.pem"
# The pin is the trust, not the dates; a long life avoids an expiry nobody would notice
VALIDITY = dt.timedelta(days=3650)


@dataclass(frozen=True)
class Identity:
    """Paths to the PC's key and certificate, and the certificate's fingerprint."""

    key_path: Path
    cert_path: Path
    cert_der: bytes

    @property
    def fingerprint(self) -> str:
        """SHA-256 of the DER certificate, in lowercase hex."""
        return fingerprint(self.cert_der)


def fingerprint(cert_der: bytes) -> str:
    """SHA-256 of a DER certificate, in lowercase hex."""
    return hashlib.sha256(cert_der).hexdigest()


def self_signed(common_name: str) -> tuple[bytes, bytes]:
    """A new P-256 key and a certificate for it; returns (key PEM, certificate DER)."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + VALIDITY)
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return key_pem, cert.public_bytes(serialization.Encoding.DER)


def der_to_pem(cert_der: bytes) -> bytes:
    """A DER certificate as PEM."""
    return x509.load_der_x509_certificate(cert_der).public_bytes(serialization.Encoding.PEM)


def _write_private(path: Path, data: bytes) -> None:
    """Writes `path` atomically, readable by the owner only from the first byte."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_or_create(directory: Path | None = None) -> Identity:
    """The PC's identity, created on first use with the key readable by the owner only."""
    directory = config.private_dir(directory or config.config_dir())
    key_path, cert_path = directory / KEY_FILE, directory / CERT_FILE
    if not (key_path.exists() and cert_path.exists()):
        key_pem, cert_der = self_signed(f"hal-echo-show on {socket.gethostname()}")
        # The key lands first, so a crash between the two leaves no certificate without its key
        _write_private(key_path, key_pem)
        _write_private(cert_path, der_to_pem(cert_der))
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return Identity(key_path, cert_path, cert.public_bytes(serialization.Encoding.DER))
