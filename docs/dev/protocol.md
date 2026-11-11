# The protocol

The Echo and the PC exchange length-prefixed frames over the TLS link. `halecho/frames.py` and
`net/Frames.kt` implement them, and both test suites pin the same bytes.

```text
frame = length (u32, big endian) | kind (u8) | payload (length bytes, at most 1 MiB)
kind 1  JSON   one UTF-8 JSON object with a "type"
kind 2  AUDIO  turn id (u32) | sequence (u32) | 16-bit little-endian mono PCM
kind 3  BLOB   transfer id (u32) | file bytes
kind 4  TERM   terminal id (u32) | bytes: a program's output, or keys and mouse reports for it
```

## Messages from the device

The device sends the following JSON messages.

| Type | Fields | Meaning |
| --- | --- | --- |
| `hello` | `app_version`, `abi`, `muted` | First message after the handshake |
| `wake` | `turn`, `score` | The wake word was heard; `score` (0 to 1) is how far the voice rose above the room |
| `utterance` | `turn`, `text`, `followup` | The transcript of a request; `followup` means no name was needed |
| `utterance_audio`, `utterance_audio_end` | `turn`, `followup` | Around AUDIO frames, with `stt_location: pc` |
| `approval` | `turn`, `text` | The spoken answer to an approval request; empty on silence |
| `barge_in` | `turn` | The wake word was heard while HAL spoke; playback has stopped |
| `state` | `muted`, `awake` | The privacy mute or the room state changed |
| `need_model` | `name` | Send this model |
| `update_result` | `ok`, `message` | What Android's installer said |
| `ping` | `t` | Keep-alive, every 20 s |
| `crash_report` | `text` | The stack trace of the app's last crash, sent once after it restarts |
| `term_size` | `term`, `cols`, `rows` | The terminal screen's size in cells; the program starts at it, or is resized |
| `term_close` | `term` | The terminal was closed on the device (a two-second hold) |

## Messages from the PC

The PC sends the following JSON messages.

| Type | Fields | Meaning |
| --- | --- | --- |
| `welcome` | `mode`, `listener`, `models`, names | The device's settings and the models it needs, with SHA-256 |
| `floor` | `turn`, `granted` | Whether this device answers the wake word it reported |
| `state` | `state` | `thinking` while the brain works |
| `say`, `say_end` | `turn`, `seq`, `text`, `sr` | Around the AUDIO frames of one sentence |
| `turn_end` | `turn`, `finished` or `heard` | The reply is complete, interrupted, or the speech was not for Hal |
| `listen` | `turn`, `purpose`, `timeout_s` | Record the next utterance: the `request` after a bare "Hal", or an `approval` |
| `blob_begin`, `blob_end` | `id`, `purpose`, `name`, `size`, `sha256` | Around the BLOB frames of a `model` or an `update` |
| `pong`, `error` | | Keep-alive reply; a failed request |
| `view` | `name`, `term`, `title` | Show a `terminal` screen fed by TERM frames, or the `eye` again |

A terminal screen runs a program the bridge's settings name (`screens.monitor.command`); the
device can show it and type into it, but cannot choose what runs. Turn ids come from the device. A turn the PC starts itself (`hal-echo say`) sets the top bit.

## A turn

The following sequence is one request with a reply.

```text
device                          pc
wake {turn 7, score 0.8}  -->
                          <--   floor {turn 7, granted}
utterance {turn 7, text}  -->
                          <--   state thinking
                          <--   say {turn 7, seq 1, text, sr 32000}, AUDIO..., say_end
                          <--   turn_end {turn 7, finished}
(follow-up window opens when playback ends)
```
