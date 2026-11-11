# Security

This page says what hal-echo-show protects against, what it does not, and how to report a problem.

## Reporting a problem

Report a vulnerability privately to the maintainer (contact details are on the repository page),
not in a public issue. Include the version (`git describe` or the `pyproject.toml` version), what
you did and what you expected. Expect an answer within 7 days.

## What it protects against

The design assumes an attacker on your home network.

| Threat | Protection |
| --- | --- |
| Listening to your conversations on the network | Every frame is TLS 1.3. |
| Posing as the PC to an Echo, or as an Echo to the PC | Both sides pin each other's certificate at pairing; nothing else is trusted. |
| Pairing a rogue device | The code is only on the Echo's screen. CPace allows no offline guessing, each attempt is one online guess, and pairing stops after 3 wrong codes or 300 s. The PC shows each request's name and address before you type the code. |
| Spoofed mDNS announcements | mDNS supplies only an address; a wrong certificate fails the handshake. |
| Other machines reaching the bridge | The handshake refuses unpaired certificates; `hal-echo firewall` adds rules for the Echo's address only. |
| A tampered model or update | Models are checked against the SHA-256 in `halecho/models.toml`; Android installs an update only if it is signed with the installed app's key, and only after a tap. |
| Other local users on the PC | The PC's key, the device list and the control socket are readable by the owner only. |

## What it does not protect against

- **The Echo's own software.** The LineageOS build runs SELinux permissive, and its authors advise
  against keeping sensitive data on it. The device key lives in Android Keystore; whether this
  ROM's Keystore is backed by hardware is unverified. Treat an Echo as trusted as its ROM.
- **Someone in the room.** Anyone who can speak to an Echo can use its mode. Give shared rooms
  `home` mode, and use `hal-echo unpair` for a lost or sold device.
- **ADB.** On this ROM, USB debugging also opens ADB over the network. Turn it off when setup is
  done ([Set up the Echo](docs/howto/set-up-the-echo.md), step 10).
- **Personal mode is enforced at the approval step.** Desktop tools that Hal's policy runs without
  asking are not stopped ([Modes](docs/user/modes.md)).

## What leaves the Echo

The Echo sends the PC the recordings of utterances addressed to Hal: those with the wake word,
follow-ups in the few seconds after a reply, and approval answers. Other speech is dropped on the
device without being transcribed or sent. With `listener.stt_location: device` the Echo sends the
text instead of the recording. While the room is quiet the Echo measures loudness only. The bridge sends
no data anywhere but the paired devices and the model URLs in `halecho/models.toml`.

## Scope

Reports about the dependencies (hal-voice, whisper.cpp, Vosk, libsodium, the ROM) belong to those
projects; tell us when hal-echo-show's use of them makes the problem worse.
