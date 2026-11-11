# Changelog

All notable changes to hal-echo-show are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- The PC bridge, `hal-echo`: serves paired Echo Show devices with hal-voice's brain and voice.
- Pairing with a six-digit code over CPace, then TLS 1.3 with both certificates pinned.
- The Android app: HAL's eye as the home screen, a loudness gate that idles a quiet room, a Vosk
  wake word spotter, whisper.cpp speech recognition on the device, barge-in and follow-ups.
- Desk, personal and home modes; home mode is a stub for Home Assistant.
- Floor control: when several devices hear one wake word, the loudest answers.
- Speech models sent from the PC with their SHA-256, and app updates sent over the paired link.
- A Hal pack manifest with `echo_say` and `echo_devices`.
- A Whisper benchmark that runs on the Echo without installing anything.
- A speaker EQ for the Echo's small driver, applied to HAL's voice before it is sent.
