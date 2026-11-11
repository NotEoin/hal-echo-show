# Modes

Each paired Echo has a mode that decides which brain answers it and which tools that brain may
use. Set it when pairing (`hal-echo pair --mode MODE`) or later (`hal-echo mode NAME MODE`); a
change applies from the device's next connection.

| Mode | For | Brain | Tools |
| --- | --- | --- | --- |
| `desk` | Your desk, replacing hal-voice's own loop | hal-voice's `brain.mode`, unchanged | All of them, with spoken approvals |
| `personal` | A room only you use: bedroom, study | The same brain, told it is away from the desk | All but the packs in `modes.personal.denied_packs` (`desktop`) |
| `home` | A shared room: kitchen, living room | A stub for Home Assistant | None |

## Desk

The Echo takes the place of the PC's microphone and speakers. By default `hal-echo serve` stops
hal-voice's own loop (`hal-voice.service`) so the two do not both answer; set
`coexist.hal_voice_loop: true` to keep both.

## Personal

The brain is told it is speaking in a private room and cannot see the desktop. Approval requests
for a tool from a denied pack are refused without being spoken. Two limits apply:

- A denied pack's tools that Hal's policy runs without asking (its `read` tier, for example) still
  run, because the bridge sees only the requests that ask for approval. Closing this needs Hal to
  deny a pack per channel, which Hal's policy does not offer yet (checked against Hal's
  `policy/profiles.py`, 2026-11-11).
- `brain.mode: claude` is refused here: Claude Code runs on the host with your full access.

## Home

Anyone in the room can talk to it, so it reaches none of your own tools, files or accounts. It
answers that Home Assistant is not connected. `home_assistant.url` and
`home_assistant.token_file` are read and checked so the settings are ready; nothing is sent to
Home Assistant yet.
