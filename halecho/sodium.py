"""ristretto255 primitives from the system libsodium, through ctypes.

PyNaCl does not bind ristretto255 (checked with PyNaCl 1.6.2), and the pairing exchange in
`halecho.cpace` needs the same group on both ends: the Android app reaches these functions
through lazysodium. Needs libsodium 1.0.18 or later (`libsodium23` on Debian and Ubuntu).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import functools

POINT_BYTES = 32
HASH_BYTES = 64
SCALAR_BYTES = 32


class SodiumUnavailable(RuntimeError):
    """libsodium is missing or too old to have ristretto255."""


@functools.cache
def _lib() -> ctypes.CDLL:
    name = ctypes.util.find_library("sodium")
    if not name:
        raise SodiumUnavailable(
            "libsodium not found: install libsodium23 (Debian, Ubuntu) or libsodium (Fedora, Arch)"
        )
    lib = ctypes.CDLL(name)
    if lib.sodium_init() < 0:
        raise SodiumUnavailable("sodium_init() failed")
    if not hasattr(lib, "crypto_core_ristretto255_from_hash"):
        raise SodiumUnavailable(f"{name} has no ristretto255: libsodium 1.0.18 or later is needed")
    buf = ctypes.c_char_p
    lib.crypto_core_ristretto255_from_hash.argtypes = [buf, buf]
    lib.crypto_core_ristretto255_is_valid_point.argtypes = [buf]
    lib.crypto_core_ristretto255_scalar_random.argtypes = [buf]
    lib.crypto_core_ristretto255_scalar_random.restype = None
    lib.crypto_scalarmult_ristretto255.argtypes = [buf, buf, buf]
    return lib


def available() -> str | None:
    """None when ristretto255 is usable, else the reason it is not."""
    try:
        _lib()
    except (SodiumUnavailable, OSError) as exc:
        return str(exc)
    return None


def point_from_hash(digest: bytes) -> bytes:
    """Maps a 64-byte hash to a ristretto255 point (RFC 9496 one-way map)."""
    if len(digest) != HASH_BYTES:
        raise ValueError(f"expected {HASH_BYTES} bytes, got {len(digest)}")
    out = ctypes.create_string_buffer(POINT_BYTES)
    if _lib().crypto_core_ristretto255_from_hash(out, digest) != 0:
        raise ValueError("ristretto255 from_hash failed")
    return out.raw


def is_valid_point(point: bytes) -> bool:
    """True when `point` is the canonical encoding of a ristretto255 group element."""
    return len(point) == POINT_BYTES and _lib().crypto_core_ristretto255_is_valid_point(point) == 1


def scalar_random() -> bytes:
    """A uniformly random non-zero scalar, from libsodium's CSPRNG."""
    out = ctypes.create_string_buffer(SCALAR_BYTES)
    _lib().crypto_core_ristretto255_scalar_random(out)
    return out.raw


def scalarmult(scalar: bytes, point: bytes) -> bytes:
    """Returns `scalar` times `point`.

    Raises:
        ValueError: the point is not valid, or the product is the identity element.
    """
    if len(scalar) != SCALAR_BYTES or not is_valid_point(point):
        raise ValueError("invalid scalar or point")
    out = ctypes.create_string_buffer(POINT_BYTES)
    # libsodium returns -1 when the result is the identity, which CPace must refuse
    if _lib().crypto_scalarmult_ristretto255(out, scalar, point) != 0:
        raise ValueError("scalar multiplication gave the identity element")
    return out.raw
