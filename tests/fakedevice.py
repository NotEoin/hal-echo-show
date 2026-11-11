"""A stand-in for the Android app: its own key, pairing, and the pinned TLS link."""

from __future__ import annotations

import asyncio
import datetime as dt
import ssl
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from halecho import frames
from halecho.identity import der_to_pem


def keystore_like_cert(common_name: str) -> tuple[bytes, bytes]:
    """A P-256 key and a self-signed certificate shaped like Android Keystore's.

    Keystore marks the key for signing only and adds no basic constraints, so this checks
    that the PC accepts such a certificate as its own trust anchor.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.UTC)
    usage = x509.KeyUsage(
        digital_signature=True,
        content_commitment=False,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=False,
        crl_sign=False,
        encipher_only=False,
        decipher_only=False,
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(usage, critical=True)
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return key_pem, cert.public_bytes(serialization.Encoding.DER)


class FakeDevice:
    """Pairs with and talks to a bridge the way `Link.kt` does."""

    def __init__(self, directory: Path, name: str = "Kitchen") -> None:
        self.name = name
        key_pem, self.cert_der = keystore_like_cert(f"device {name}")
        directory.mkdir(parents=True, exist_ok=True)
        self.key_path = directory / f"{name}-key.pem"
        self.cert_path = directory / f"{name}-cert.pem"
        self.key_path.write_bytes(key_pem)
        self.cert_path.write_bytes(der_to_pem(self.cert_der))
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.audio: list[tuple[int, int, bytes]] = []

    def client_context(self, pc_cert_der: bytes) -> ssl.SSLContext:
        """TLS 1.3, this device's certificate, and only the pinned PC certificate trusted."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.check_hostname = False
        ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        ctx.load_verify_locations(cadata=der_to_pem(pc_cert_der).decode())
        ctx.load_cert_chain(self.cert_path, self.key_path)
        return ctx

    async def connect(self, port: int, pc_cert_der: bytes) -> None:
        self.reader, self.writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=self.client_context(pc_cert_der)
        )

    async def send(self, msg: dict[str, Any]) -> None:
        assert self.writer is not None
        self.writer.write(frames.encode_json(msg))
        await self.writer.drain()

    async def send_raw(self, data: bytes) -> None:
        assert self.writer is not None
        self.writer.write(data)
        await self.writer.drain()

    async def frame(self, timeout: float = 5.0) -> frames.Frame:
        assert self.reader is not None
        return await asyncio.wait_for(frames.read_frame(self.reader), timeout)

    async def expect(self, kind: str, timeout: float = 5.0) -> dict[str, Any]:
        """The next JSON message of `kind`; audio frames on the way are kept in `audio`."""
        while True:
            frame = await self.frame(timeout)
            if frame.kind == frames.AUDIO:
                self.audio.append(frame.audio())
                continue
            if frame.kind == frames.BLOB:
                continue
            msg = frame.json()
            if msg["type"] == kind:
                return msg

    async def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
