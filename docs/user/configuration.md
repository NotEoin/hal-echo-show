# Configuration

The bridge reads `~/.config/hal-echo-show/config.yaml`. It may set only keys that exist in the
packaged defaults (`halecho/config.yaml`, which documents each one); an unknown key stops the
bridge with its name. The brain, the voice and GPU sharing are hal-voice's settings, in
`~/.config/hal-voice/config.yaml`.

## Settings

The following table lists the settings you are most likely to change.

| Key | Default | What it does |
| --- | --- | --- |
| `server.port` | `47800` | The encrypted link's port |
| `server.pair_port` | `47801` | The pairing port, open only while `hal-echo pair` runs |
| `server.name` | the host name | The name the Echo shows for the PC |
| `pairing.max_attempts` | `3` | Wrong codes before `hal-echo pair` stops |
| `listener.awake_s` | `300` | After the last sound, how long the Echo listens for its name |
| `listener.followup_s` | `8` | After a reply, how long you can carry on without the name |
| `listener.stt_model` | `whisper-base.en-q8_0` | The Echo's Whisper model, from `halecho/models.toml` |
| `listener.stt_location` | `device` | `pc` sends recordings to hal-voice's faster-whisper instead |
| `listener.barge_in` | `auto` | Whether "Hal" stops HAL mid-reply: `auto` only with an echo canceller (not on the Echo Show 5); a tap on the eye always does |
| `listener.wake_phrases` | `hey hal`, `hal`, `okay hal` | What the spotter listens for |
| `speaker_eq.*` | on | EQ for the Echo's small speaker: cuts below `highpass_hz` (150), trims `mud_hz` (350), lifts `presence_hz` (3500) and `air_hz` (8000); `hal-echo say` plays a line to compare |
| `floor.window_ms` | `350` | Wake reports this close together count as one, and the loudest answers |
| `coexist.hal_voice_loop` | `false` | `true` lets hal-voice's own loop run alongside |
| `modes.personal.denied_packs` | `[desktop]` | Packs personal mode refuses |

## Files

The bridge keeps its state in the following places.

| Path | What it holds |
| --- | --- |
| `~/.config/hal-echo-show/pc-key.pem` | The PC's private key (mode 0600) |
| `~/.config/hal-echo-show/devices.json` | Paired devices and their pinned certificates (mode 0600) |
| `~/.cache/hal-echo-show/models/` | Downloaded speech models |
| `$XDG_RUNTIME_DIR/hal-echo-show.sock` | The control socket for `say`, `devices` and `push-update` |
