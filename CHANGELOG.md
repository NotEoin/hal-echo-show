# Changelog

All notable changes to hal-echo-show are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- A hardware monitor: "Hey Hal, open the hardware monitor" runs btop on the PC and shows it in a
  terminal on the Echo, with a small eye beside it; "close the monitor", a tap on that eye, the
  room going quiet or ten minutes bring the eye back. Desk and personal mode only.
- A third-party notices file, and the Apache 2.0 licence text inside the app.

### Fixed

- The Android build image builds on GitHub's runners, whose default Docker build network
  cannot resolve DNS.

## [0.1.0] - 2026-11-11

First release, run end to end on an Echo Show 5 (2019) with LineageOS 18.1.

### Added

- The PC bridge, `hal-echo`: serves paired Echo Show devices with hal-voice's brain and voice, as a
  systemd user service. `hal-echo doctor` checks libsodium, hal-voice, the port, the models and ufw.
- Pairing with a six-digit code shown on the Echo, over CPace (draft-irtf-cfrg-cpace-21, checked
  against its test vectors), then TLS 1.3 with both certificates pinned. Pairing stops after three
  wrong codes.
- The Android app: HAL's eye as the home screen from boot, a loudness gate that idles a quiet room,
  a Vosk wake word spotter, follow-ups without the name, spoken approvals, and tap to stop.
- Speech recognition on the PC by default (`listener.stt_location: pc`), or Whisper on the Echo
  (`device`), measured at about 9 s per request on an Echo Show 5.
- Desk, personal and home modes; personal refuses hal-tools' `desktop` pack at the approval step,
  and home mode is a stub for Home Assistant.
- Floor control: when several devices hear one wake word, the loudest answers.
- Speech models sent from the PC with their SHA-256, and app updates sent over the paired link
  (`hal-echo push-update`), installed after a tap on the Echo.
- A speaker EQ for the Echo's small driver, applied to HAL's voice before it is sent.
- The eye: a film-style lens with a slow resting breath, captions in Geist Mono, and a red wash.
- A Hal pack manifest with `echo_say` and `echo_devices`.
- A Whisper benchmark that runs on the Echo without installing anything.

[0.1.0]: https://github.com/NotEoin/hal-echo-show/releases/tag/v0.1.0
