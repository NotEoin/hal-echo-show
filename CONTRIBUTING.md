# Contributing

This page covers testing a change and the rules a change follows.

## Set up and test

The following commands are the ones CI runs.

```bash
uv run --frozen --extra test pytest -q   # the bridge's hermetic tests (needs libsodium)
ruff check . && ruff format --check .    # lint and format
scripts/ascii-check.sh                   # tracked text must be ASCII
android/build.sh test                    # the app's unit tests and lint, in Docker
```

## Rules

- One logical change per commit, with its tests and doc updates. Every commit passes the commands
  above.
- Commit subjects are one line, `<area>: <what>`: `pairing: limit wrong codes per window`. No body.
- Every module and source file opens with a comment or docstring saying what it is for; public
  functions have a one-line docstring and type hints.
- Comments say why, not what. Every suppression names its rule and gives a reason.
- Every network call, subprocess and lock wait has a timeout.
- ASCII only in code, docs and commit messages. Write non-ASCII text as escapes, or XML entities in
  Android resources.
- A change to the protocol changes `halecho/frames.py`, `net/Frames.kt`, both tests and
  `docs/dev/protocol.md` together.
- A bug fix comes with a test that fails without it.
- Fixtures are synthetic: no recordings of real people, no secrets.

## Reporting a security problem

See [SECURITY.md](SECURITY.md).
