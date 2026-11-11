"""CPace over ristretto255 with SHA-512: the password-authenticated key exchange used to pair.

Follows draft-irtf-cfrg-cpace-21 (cipher suite CPACE-RISTR255-SHA512, initiator-responder
transcript) and its section 10.4 key confirmation; `tests/test_cpace.py` checks the draft's
appendix B.3 test vectors. The Android app implements the same steps in `crypto/CPace.kt`.

The pairing code is the password (PRS). A party that does not know it learns nothing it can
test offline: each attempt costs an attacker one online guess.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from . import sodium

DSI = b"CPaceRistretto255"
DSI_ISK = DSI + b"_ISK"
HASH_BLOCK_BYTES = 128  # SHA-512 input block size, s_in_bytes in the draft
MAC_LABEL = b"CPaceMac"


def prepend_len(data: bytes) -> bytes:
    """`data` prefixed with its length in LEB128."""
    length = len(data)
    encoded = bytearray()
    while True:
        if length < 128:
            encoded.append(length)
        else:
            encoded.append((length & 0x7F) + 0x80)
        length >>= 7
        if length == 0:
            break
    return bytes(encoded) + data


def lv_cat(*parts: bytes) -> bytes:
    """Each part length-prefixed, then concatenated."""
    return b"".join(prepend_len(p) for p in parts)


def generator_string(prs: bytes, ci: bytes, sid: bytes) -> bytes:
    """The hash input for the generator, zero-padded so PRS ends the first hash block."""
    zpad = max(0, HASH_BLOCK_BYTES - 1 - len(prepend_len(prs)) - len(prepend_len(DSI)))
    return lv_cat(DSI, prs, bytes(zpad), ci, sid)


def calculate_generator(prs: bytes, ci: bytes, sid: bytes) -> bytes:
    """The password-derived generator g."""
    return sodium.point_from_hash(hashlib.sha512(generator_string(prs, ci, sid)).digest())


def transcript_ir(ya: bytes, ada: bytes, yb: bytes, adb: bytes) -> bytes:
    """The initiator-responder transcript: the initiator's message first."""
    return lv_cat(ya, ada) + lv_cat(yb, adb)


def intermediate_key(sid: bytes, k: bytes, ya: bytes, ada: bytes, yb: bytes, adb: bytes) -> bytes:
    """ISK: the shared secret bound to both messages and their associated data."""
    return hashlib.sha512(lv_cat(DSI_ISK, sid, k) + transcript_ir(ya, ada, yb, adb)).digest()


def confirmation_tag(isk: bytes, sid: bytes, y: bytes, ad: bytes) -> bytes:
    """The key confirmation tag over one party's own message (draft section 10.4)."""
    mac_key = hashlib.sha512(MAC_LABEL + sid + isk).digest()
    return hmac.new(mac_key, lv_cat(y, ad), hashlib.sha512).digest()


class PairingFailed(Exception):
    """The peer used another code, or sent a malformed or hostile message."""


@dataclass(frozen=True)
class Confirmed:
    """The outcome of a CPace run: the key and the tags each side sends."""

    isk: bytes
    own_tag: bytes
    peer_tag: bytes

    def check(self, tag: bytes) -> None:
        """Raises `PairingFailed` unless `tag` is the tag the peer must send."""
        if not hmac.compare_digest(tag, self.peer_tag):
            raise PairingFailed("the confirmation tag does not match: wrong code")


class CPace:
    """One side of a CPace run.

    Args:
        prs: the shared code.
        ci: the channel identifier, the same on both sides.
        sid: the session id, chosen at random by the initiator.
        ad: this side's associated data, authenticated by the exchange.
        scalar: a fixed secret scalar, for test vectors only.
    """

    def __init__(
        self, prs: bytes, ci: bytes, sid: bytes, ad: bytes, scalar: bytes | None = None
    ) -> None:
        self.sid = sid
        self.ad = ad
        self._y = scalar if scalar is not None else sodium.scalar_random()
        self.message = sodium.scalarmult(self._y, calculate_generator(prs, ci, sid))

    def finish(self, peer_message: bytes, peer_ad: bytes, initiator: bool) -> Confirmed:
        """Derives the shared key from the peer's message.

        Raises:
            PairingFailed: the peer's message is not a valid point, or gives the identity.
        """
        try:
            k = sodium.scalarmult(self._y, peer_message)
        except ValueError as exc:
            raise PairingFailed(f"bad peer message: {exc}") from exc
        if initiator:
            isk = intermediate_key(self.sid, k, self.message, self.ad, peer_message, peer_ad)
        else:
            isk = intermediate_key(self.sid, k, peer_message, peer_ad, self.message, self.ad)
        return Confirmed(
            isk=isk,
            own_tag=confirmation_tag(isk, self.sid, self.message, self.ad),
            peer_tag=confirmation_tag(isk, self.sid, peer_message, peer_ad),
        )
