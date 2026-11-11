#!/usr/bin/env bash
# Sets up the PC side: a virtualenv with hal-voice and this bridge, and optionally the
# systemd user unit. Run from the checkout:
#   ./setup-pc.sh [--hal-voice PATH] [--unit] [--yes]
# PATH defaults to a hal-voice checkout next to this one (../hal-voice).
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"

hal_voice="$ROOT/../hal-voice"
unit=false
assume_yes=false
while [ $# -gt 0 ]; do
    case "$1" in
        --hal-voice) hal_voice="$2"; shift 2 ;;
        --unit) unit=true; shift ;;
        --yes) assume_yes=true; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ ! -f "$hal_voice/pyproject.toml" ]; then
    echo "No hal-voice checkout at $hal_voice." >&2
    echo "Clone https://github.com/NotEoin/hal-voice and set it up first, or pass --hal-voice PATH." >&2
    exit 1
fi
hal_voice="$(cd "$hal_voice" && pwd)"

if ! ldconfig -p 2>/dev/null | grep -q libsodium; then
    echo "libsodium is missing: install libsodium23 (Debian, Ubuntu) or libsodium (Fedora, Arch)." >&2
    exit 1
fi

if ! $assume_yes; then
    echo "This creates $ROOT/.venv with hal-voice ($hal_voice) and hal-echo-show."
    read -r -p "Continue? [y/N] " answer
    [ "$answer" = "y" ] || exit 1
fi

if command -v uv > /dev/null; then
    uv venv --python 3.12 "$ROOT/.venv"
    VIRTUAL_ENV="$ROOT/.venv" uv pip install -e "$hal_voice" -e "$ROOT"
else
    python3.12 -m venv "$ROOT/.venv"
    "$ROOT/.venv/bin/pip" install -e "$hal_voice" -e "$ROOT"
fi

if $unit; then
    units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$units"
    sed "s|@ROOT@|$ROOT|g" systemd/hal-echo.service > "$units/hal-echo.service"
    systemctl --user daemon-reload
    echo "Installed $units/hal-echo.service. Start it with: systemctl --user enable --now hal-echo.service"
fi

echo
echo "Done. Next:"
echo "  $ROOT/.venv/bin/hal-echo doctor"
echo "  $ROOT/.venv/bin/hal-echo pair"
