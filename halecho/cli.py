"""`hal-echo`: run the bridge, pair and manage devices, and push models and updates.

hal-echo serve                       run the bridge (the systemd unit runs this)
hal-echo pair [--mode MODE]          pair a device with the code on its screen
hal-echo devices                     list paired devices
hal-echo mode NAME MODE              set a device's mode: desk, personal or home
hal-echo rename NAME NEW             rename a device
hal-echo unpair NAME                 forget a device; its certificate stops working
hal-echo say TEXT [--device NAME]    speak a line on one device, or all
hal-echo push-update APK [--device NAME]
hal-echo models [NAME ...]           download speech models ahead of time
hal-echo firewall [--address IP]     print the ufw rules the bridge needs
hal-echo doctor                      check the setup
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import subprocess
import sys

from . import __version__, config, models
from .registry import MODES, Registry, RegistryError

log = logging.getLogger("halecho")

SYSTEMCTL_TIMEOUT_S = 20
HAL_VOICE_UNIT = "hal-voice.service"


def _settings() -> config.Cfg:
    try:
        return config.load()
    except config.ConfigError as exc:
        sys.exit(f"hal-echo: {exc}")


def cmd_serve(_args: argparse.Namespace) -> int:
    """Runs the bridge until interrupted."""
    from .backend import BackendUnavailable, HalVoiceBackend
    from .identity import load_or_create
    from .server import Bridge

    settings = _settings()
    if not settings.get("coexist.hal_voice_loop"):
        _stop_hal_voice_loop()
    try:
        backend = HalVoiceBackend()
    except BackendUnavailable as exc:
        print(f"hal-echo: {exc}", file=sys.stderr)
        return 1
    bridge = Bridge(settings, load_or_create(), Registry(), backend)
    try:
        asyncio.run(bridge.serve())
    except KeyboardInterrupt:
        log.info("stopped")
    finally:
        backend.close()
    return 0


def _stop_hal_voice_loop() -> None:
    """Stops hal-voice's own loop, so the PC's microphone does not answer as well."""
    try:
        active = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", HAL_VOICE_UNIT],
            timeout=SYSTEMCTL_TIMEOUT_S,
            check=False,
        )
        if active.returncode == 0:
            log.info("stopping %s (coexist.hal_voice_loop is false)", HAL_VOICE_UNIT)
            subprocess.run(
                ["systemctl", "--user", "stop", HAL_VOICE_UNIT],
                timeout=SYSTEMCTL_TIMEOUT_S,
                check=False,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        # Without systemd there is no hal-voice unit to stop; the bridge still serves
        log.warning("could not check %s: %s", HAL_VOICE_UNIT, exc)


def cmd_pair(args: argparse.Namespace) -> int:
    """Waits for one device and pairs it with the code its screen shows."""
    from .discovery import Announcer
    from .identity import load_or_create
    from .pairing import PairingServer
    from .server import server_name

    settings = _settings()
    identity = load_or_create()
    mode = args.mode or str(settings.get("pairing.default_mode"))
    name = server_name(settings)
    pair_port = int(settings.get("server.pair_port"))

    async def ask_code(device: str, address: str) -> str | None:
        print(f"\nPairing request from '{device}' at {address}.")
        code = await asyncio.to_thread(input, "Type the code shown on its screen (blank refuses): ")
        return code.strip() or None

    async def run() -> int:
        server = PairingServer(
            identity,
            Registry(),
            ask_code,
            mode,
            name,
            int(settings.get("server.port")),
            int(settings.get("pairing.max_attempts")),
        )
        print(f"Waiting for a device on port {pair_port} as '{name}'.")
        print("On the Echo: hold the eye for two seconds, then tap Pair.")
        async with Announcer(name, 0, identity.fingerprint, True, pair_port):
            dev = await server.run(
                str(settings.get("server.host")), pair_port, float(settings.get("pairing.window_s"))
            )
        if dev is None:
            print("No device paired.")
            return 1
        print(f"Paired '{dev.name}' in {dev.mode} mode. Its certificate: {dev.fingerprint}")
        return 0

    return asyncio.run(run())


def cmd_devices(_args: argparse.Namespace) -> int:
    """Lists paired devices and whether each is connected."""
    from . import modes
    from .server import control_request

    devices = Registry().all()
    if not devices:
        print("No paired devices. Run `hal-echo pair`.")
        return 0
    try:
        connected = asyncio.run(control_request({"cmd": "status"}, 5.0)).get("connected", {})
    except (ConnectionError, OSError, TimeoutError):
        connected = None
    for dev in devices:
        state = "?" if connected is None else ("online" if dev.id in connected else "offline")
        print(
            f"{dev.name:<20} {dev.mode:<9} {state:<8} {dev.last_address or '-':<16} {modes.describe(dev.mode)}"
        )
    if connected is None:
        print("(the bridge is not running, so the online state is unknown)")
    return 0


def cmd_mode(args: argparse.Namespace) -> int:
    """Sets a device's mode; it applies from the device's next connection."""
    dev = Registry().set_mode(args.name, args.mode)
    print(f"'{dev.name}' is in {dev.mode} mode from its next connection.")
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    """Renames a device."""
    dev = Registry().rename(args.name, args.new_name)
    print(f"Renamed to '{dev.name}'.")
    return 0


def cmd_unpair(args: argparse.Namespace) -> int:
    """Forgets a device."""
    dev = Registry().remove(args.name)
    print(f"Unpaired '{dev.name}'. Its certificate is refused from the next connection on.")
    return 0


def _control(cmd: dict, timeout_s: float = 300.0) -> int:
    from .server import control_request

    try:
        reply = asyncio.run(control_request(cmd, timeout_s))
    except ConnectionError as exc:
        print(f"hal-echo: {exc}", file=sys.stderr)
        return 1
    if not reply.get("ok"):
        print(f"hal-echo: {reply.get('error') or 'no connected device matched'}", file=sys.stderr)
        return 1
    print(f"Sent to: {', '.join(reply.get('devices', []))}")
    return 0


def cmd_say(args: argparse.Namespace) -> int:
    """Speaks a line on one connected device, or on all of them."""
    return _control({"cmd": "say", "text": args.text, "device": args.device}, 30.0)


def cmd_push_update(args: argparse.Namespace) -> int:
    """Sends an APK; the device asks for a tap on its screen before installing it."""
    from pathlib import Path

    path = Path(args.apk).resolve()
    return _control({"cmd": "push_update", "path": str(path), "device": args.device})


def cmd_models(args: argparse.Namespace) -> int:
    """Downloads speech models into the cache ahead of time."""
    settings = _settings()
    names = args.names or [settings.get("listener.stt_model"), settings.get("listener.wake_model")]
    for name in names:
        try:
            model, path = models.ensure(str(name))
        except models.ModelError as exc:
            print(f"hal-echo: {exc}", file=sys.stderr)
            return 1
        print(f"{model.name}: {path}")
    return 0


def cmd_firewall(args: argparse.Namespace) -> int:
    """Prints the ufw rules that let each device, and only it, reach the bridge."""
    settings = _settings()
    port, pair_port = settings.get("server.port"), settings.get("server.pair_port")
    addresses = [args.address] if args.address else []
    addresses += [d.last_address for d in Registry().all() if d.last_address]
    if not addresses:
        print("No device addresses known yet. Pass --address with the Echo's reserved IP.")
        return 1
    print("# Run these yourself; the bridge never changes the firewall.")
    for address in dict.fromkeys(addresses):
        print(f"sudo ufw allow from {address} to any port {port} proto tcp comment 'hal-echo-show'")
        print(
            f"sudo ufw allow from {address} to any port {pair_port} proto tcp comment 'hal-echo-show pairing'"
        )
    print(
        "sudo ufw allow from any to any port 5353 proto udp comment 'mDNS'  # optional: discovery"
    )
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Checks the setup and prints what to fix."""
    from . import doctor

    return doctor.run(_settings())


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hal-echo", description="Hal on an Echo Show: the PC bridge.")
    p.add_argument("--version", action="version", version=f"hal-echo-show {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="log debug messages")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the bridge").set_defaults(func=cmd_serve)
    pair = sub.add_parser("pair", help="pair a device with the code on its screen")
    pair.add_argument("--mode", choices=MODES)
    pair.set_defaults(func=cmd_pair)
    sub.add_parser("devices", help="list paired devices").set_defaults(func=cmd_devices)
    mode = sub.add_parser("mode", help="set a device's mode")
    mode.add_argument("name")
    mode.add_argument("mode", choices=MODES)
    mode.set_defaults(func=cmd_mode)
    rename = sub.add_parser("rename", help="rename a device")
    rename.add_argument("name")
    rename.add_argument("new_name")
    rename.set_defaults(func=cmd_rename)
    unpair = sub.add_parser("unpair", help="forget a device")
    unpair.add_argument("name")
    unpair.set_defaults(func=cmd_unpair)
    say = sub.add_parser("say", help="speak a line on connected devices")
    say.add_argument("text")
    say.add_argument("--device")
    say.set_defaults(func=cmd_say)
    update = sub.add_parser("push-update", help="send a new app build to devices")
    update.add_argument("apk")
    update.add_argument("--device")
    update.set_defaults(func=cmd_push_update)
    mdl = sub.add_parser("models", help="download speech models ahead of time")
    mdl.add_argument("names", nargs="*", metavar="NAME", help="default: the configured models")
    mdl.set_defaults(func=cmd_models)
    fw = sub.add_parser("firewall", help="print the ufw rules the bridge needs")
    fw.add_argument("--address", help="a device address not yet seen by the bridge")
    fw.set_defaults(func=cmd_firewall)
    sub.add_parser("doctor", help="check the setup").set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    """Runs one `hal-echo` command; returns its exit status."""
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return int(args.func(args))
    except RegistryError as exc:
        print(f"hal-echo: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
