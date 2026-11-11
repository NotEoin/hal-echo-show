"""mDNS announcement, so a device finds the PC after its address changes.

The announcement is a hint, not trust: a device connects only to the certificate it pinned
at pairing, so a spoofed announcement leads to a failed handshake. The TXT record carries
the first 16 hex digits of that fingerprint so a device can tell several PCs apart.
"""

from __future__ import annotations

import logging
import socket

from zeroconf import IPVersion
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

log = logging.getLogger(__name__)

SERVICE_TYPE = "_hal-echo._tcp.local."
FINGERPRINT_HINT_CHARS = 16
# Connecting a UDP socket sends nothing; it only makes the kernel pick the outgoing interface.
ROUTE_PROBE = ("192.0.2.1", 9)  # TEST-NET-1 (RFC 5737), never routed


def lan_address() -> str:
    """The IPv4 address of the interface that carries the default route."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(ROUTE_PROBE)
            return str(sock.getsockname()[0])
        except OSError:
            return "127.0.0.1"


class Announcer:
    """Announces one service instance for as long as it is open."""

    def __init__(
        self, name: str, port: int, fingerprint: str, pairing: bool, pair_port: int
    ) -> None:
        self.info = AsyncServiceInfo(
            SERVICE_TYPE,
            f"{name}{' (pairing)' if pairing else ''}.{SERVICE_TYPE}",
            port=pair_port if pairing else port,
            properties={
                "v": "1",
                "fp": fingerprint[:FINGERPRINT_HINT_CHARS],
                "pair": "1" if pairing else "0",
            },
            parsed_addresses=[lan_address()],
            server=f"{socket.gethostname()}.local.",
        )
        self._zc: AsyncZeroconf | None = None

    async def __aenter__(self) -> Announcer:
        self._zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        try:
            await self._zc.async_register_service(self.info, allow_name_change=True)
        except OSError as exc:
            # mDNS is only a hint; paired devices still reach the bridge at their saved address
            log.warning("mDNS announcement failed (%s); devices use their saved address", exc)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._zc is not None:
            await self._zc.async_unregister_all_services()
            await self._zc.async_close()
