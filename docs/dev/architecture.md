# How hal-echo-show is put together

hal-echo-show has two halves: an Android app on the Echo, which listens and plays, and a Python
bridge on the PC, which thinks and speaks through hal-voice. This page maps the code; the wire
format is in [protocol.md](protocol.md) and the security design in [pairing.md](pairing.md).

## The PC: `halecho`

The bridge's modules divide the work as follows.

| Module | Responsibility |
| --- | --- |
| `server` | Accepts connections, completes TLS with the registry's certificates, runs the control socket |
| `session` | One connected device: its messages, its brain, its turns, files sent to it |
| `pairing`, `cpace`, `sodium` | The pairing exchange; ristretto255 from the system libsodium |
| `tls`, `identity`, `registry` | The PC's key and certificate, the paired devices, the pinned TLS context |
| `floor` | Chooses one device when several hear the same wake word |
| `screens`, `terminal` | Screen commands matched before the brain; a program in a pseudo-terminal, streamed as TERM frames |
| `modes`, `homeassistant` | The brain for each mode; the Home Assistant stub |
| `backend` | The only module that imports hal-voice: brains, voice, GPU sharing, faster-whisper |
| `models` | The speech-model catalogue (`models.toml`) and its checked download cache |
| `discovery` | The mDNS announcement |
| `cli`, `doctor`, `tools`, `hubtool` | `hal-echo`, its checks, and the Hal pack's tools |

Design points:

- hal-voice is a library here, imported only by `backend`, so pairing, the protocol and the tests
  run without it. `tests/conftest.py` fakes the backend.
- Brains are blocking iterators. Each session runs its turns on one worker thread and sends frames
  back through the event loop; a disconnect mid-turn raises `SessionClosed` in that thread.
- Each device gets its own brain, so conversations in different rooms do not mix.
- GPT-SoVITS synthesises one request at a time; two rooms answering at once take turns.

## The Echo: `io.github.noteoin.halecho`

The app's classes divide the work as follows.

| Class | Responsibility |
| --- | --- |
| `HalService` | The foreground service: microphone, speaker, link and models, joined through `Listener` |
| `listen.Listener` | Which utterances are for Hal; wake, floor, follow-up, approval and barge-in |
| `listen.RoomState`, `listen.Segmenter` | Asleep or awake; cutting the stream into utterances |
| `audio.Capture`, `audio.Player`, `audio.Levels` | 20 ms microphone frames; streamed playback; loudness and mute |
| `stt.VoskSpotter`, `stt.Whisper` | The wake word (Vosk with a grammar); requests (whisper.cpp over JNI) |
| `net.Link`, `net.Pinning`, `net.Discovery` | The pinned TLS connection, reconnecting; mDNS |
| `net.Frames`, `net.BlobReceiver` | The wire format; models and updates, hash-checked |
| `crypto.CPace`, `crypto.Pairing`, `crypto.DeviceIdentity` | Pairing; the Keystore key |
| `HomeActivity`, `PairActivity`, `ui.EyeView` | The eye, the menu, the pairing screen |
| `ui.RemoteTerminalView`, `ui.TerminalBus` | A terminal fed from the PC through Termux's emulator and renderer; the hand-off between service and screen |
| `update.Updater` | Installs an update the PC sent, after a tap |

Design points:

- An asleep room costs one loudness measurement per frame. The spotter runs only while the room
  is awake, and Whisper only on an utterance that is for Hal.
- `Listener` takes its collaborators as interfaces, so `ListenerTest` drives it on the JVM.
- Models are not in the APK. The PC sends them when the device first asks, so an update is about
  28 MB and the model choice is a setting on the PC.
- whisper.cpp is fetched at a pinned release with its SHA-256 (`app/src/main/cpp/CMakeLists.txt`).

## Test

The commands below run every hermetic test on both sides.

```bash
uv run --frozen --extra test pytest -q    # the bridge, with a fake backend and a fake device
android/build.sh test                     # the app's unit tests and lint, in Docker
```

`tests/test_personal_mode.py` also runs against hal-voice's real ACP brain when hal-voice is
installed in the test environment, and is skipped otherwise.
