# Pairing and the encrypted link

This page describes how a device and the PC come to trust each other, and how the link is
protected after that. The threat model is in [SECURITY.md](../../SECURITY.md).

## Pairing

Pairing runs CPace (draft-irtf-cfrg-cpace-21, ristretto255 with SHA-512), a password-authenticated
key exchange, with the six-digit code as the password. Both implementations pass the draft's
appendix B.3 test vectors (`tests/test_cpace.py`, `CPaceTest.kt`).

```text
device -> pc   pair_hello    {sid, name, cert, y}     device is the initiator; sid is 16 random bytes
               (the person types the code on the PC)
pc -> device   pair_reply    {name, cert, y, tag}
device -> pc   pair_confirm  {tag}
pc -> device   pair_done     {id, name, mode, port}
```

- Each side's associated data is its own certificate, so the confirmation tags (section 10.4 of
  the draft) prove both certificates came from someone who knew the code.
- Someone who records the exchange learns nothing they can test offline. An active attacker gets
  one guess per attempt; the PC counts an attempt as soon as it has used the code, even if the
  peer then hangs up, and stops after `pairing.max_attempts` (3).
- The pairing port is open only while `hal-echo pair` runs, for at most `pairing.window_s` (300 s).
- The device shows a fresh code after every failed attempt.

The PC's libsodium is reached through `ctypes` (`halecho/sodium.py`), because PyNaCl does not bind
ristretto255. The app uses lazysodium 5.1, whose 5.2 release ships Java 21 class files.

## The link

After pairing, every connection is TLS 1.3 with a certificate on both sides:

- The PC's key is ECDSA P-256 in `~/.config/hal-echo-show/pc-key.pem`; the device's is in Android
  Keystore and never leaves it.
- The PC loads each paired certificate as its own trust anchor
  (`VERIFY_X509_PARTIAL_CHAIN`), so the handshake fails for any other client, and checks the
  fingerprint against the registry again before a session starts. The context is rebuilt for each
  connection, so `hal-echo unpair` takes effect at once.
- The device's trust manager accepts exactly one certificate, by SHA-256.
- No certificate authority, host name or date is involved. mDNS only supplies an address.

`tests/fakedevice.py` makes certificates shaped like Keystore's (signing-only key usage, no basic
constraints) to show the PC accepts them as anchors.
