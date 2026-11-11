"""The paired devices: each one's name, mode and pinned certificate, in `devices.json`.

The file is the PC's whole trust decision: a device connects only if its certificate is
listed here. It is written atomically and kept readable by the owner only.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from . import config
from .identity import fingerprint

FILE = "devices.json"
MODES = ("desk", "personal", "home")
MAX_NAME_CHARS = 40


class RegistryError(ValueError):
    """An unknown device, a bad mode, or a name that is already taken."""


@dataclass(frozen=True)
class Device:
    """One paired device."""

    id: str
    name: str
    mode: str
    cert_der_hex: str
    paired_at: str
    last_address: str | None = None

    @property
    def cert_der(self) -> bytes:
        """The pinned certificate, DER."""
        return bytes.fromhex(self.cert_der_hex)

    @property
    def fingerprint(self) -> str:
        """SHA-256 of the pinned certificate."""
        return fingerprint(self.cert_der)


def device_id(cert_der: bytes) -> str:
    """A short stable id derived from the certificate."""
    return fingerprint(cert_der)[:16]


def utc_now() -> str:
    """The current time as UTC ISO 8601 with a `Z`, to the second."""
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_name(name: str) -> str:
    """A device name trimmed to printable ASCII and `MAX_NAME_CHARS`."""
    cleaned = "".join(ch for ch in name if 32 <= ord(ch) < 127).strip()
    return cleaned[:MAX_NAME_CHARS] or "Echo Show"


class Registry:
    """Reads and writes the paired devices."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config.config_dir() / FILE

    def all(self) -> list[Device]:
        """Every paired device, in pairing order."""
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Device(**d) for d in data.get("devices", [])]

    def find(self, key: str) -> Device:
        """The device with this id or name (names match without regard to case).

        Raises:
            RegistryError: no device matches.
        """
        for dev in self.all():
            if key == dev.id or key.lower() == dev.name.lower():
                return dev
        raise RegistryError(f"no paired device called '{key}'")

    def by_fingerprint(self, fp: str) -> Device | None:
        """The device whose pinned certificate has this fingerprint."""
        return next((d for d in self.all() if d.fingerprint == fp), None)

    def add(self, name: str, mode: str, cert_der: bytes) -> Device:
        """Pairs a device, replacing an earlier pairing of the same certificate."""
        if mode not in MODES:
            raise RegistryError(f"mode '{mode}' is not one of: {', '.join(MODES)}")
        name = self._unique(clean_name(name), device_id(cert_der))
        dev = Device(device_id(cert_der), name, mode, cert_der.hex(), utc_now())
        self._write([d for d in self.all() if d.id != dev.id] + [dev])
        return dev

    def set_mode(self, key: str, mode: str) -> Device:
        """Changes a device's mode."""
        if mode not in MODES:
            raise RegistryError(f"mode '{mode}' is not one of: {', '.join(MODES)}")
        return self._update(self.find(key).id, mode=mode)

    def rename(self, key: str, name: str) -> Device:
        """Changes a device's name."""
        dev = self.find(key)
        return self._update(dev.id, name=self._unique(clean_name(name), dev.id))

    def seen_at(self, dev_id: str, address: str) -> None:
        """Records the address a device last connected from, for `hal-echo firewall`."""
        if any(d.id == dev_id and d.last_address != address for d in self.all()):
            self._update(dev_id, last_address=address)

    def remove(self, key: str) -> Device:
        """Unpairs a device; its certificate is refused from the next handshake on."""
        dev = self.find(key)
        self._write([d for d in self.all() if d.id != dev.id])
        return dev

    def _unique(self, name: str, own_id: str) -> str:
        taken = {d.name.lower() for d in self.all() if d.id != own_id}
        candidate, n = name, 2
        while candidate.lower() in taken:
            candidate, n = f"{name} {n}", n + 1
        return candidate

    def _update(self, dev_id: str, **changes: str) -> Device:
        devices = self.all()
        for i, dev in enumerate(devices):
            if dev.id == dev_id:
                devices[i] = replace(dev, **changes)
                self._write(devices)
                return devices[i]
        raise RegistryError(f"no paired device with id '{dev_id}'")

    def _write(self, devices: list[Device]) -> None:
        directory = config.private_dir(self.path.parent)
        body = json.dumps({"devices": [asdict(d) for d in devices]}, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".devices-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
