"""The three device modes and the brain each one gets.

- `desk`: replaces hal-voice at the desk. The brain hal-voice is configured with, unchanged,
  with spoken approvals.
- `personal`: a private room. The same brain, told it is away from the desk, and any
  approval request for a pack in `modes.personal.denied_packs` (hal-tools' `desktop` pack by
  default) is refused without being spoken. Refusing happens at the approval step, so a
  denied pack's tools that Hal's policy allows without asking still run: closing that needs a
  per-channel pack rule in Hal (see `docs/user/modes.md`). Claude Code is refused here,
  because it runs on the host with the user's full access.
- `home`: a shared room. Answers from `halecho.homeassistant`, which is a stub; none of the
  user's own tools are reachable.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from typing import Any

from .backend import BackendUnavailable, Brain
from .homeassistant import HomeAssistantBrain

PERSONAL_BRAINS = ("hal", "openai")  # `claude` runs unboxed on the host
# Hal's `name [tier] pack` tool title, as hal-voice's `brains/acp.py` parses it
TOOL_TITLE = re.compile(r"^([a-z][a-z0-9_]*) \[[a-z_-]+\] ([A-Za-z0-9_.-]+)$")


def _with_persona_note(hv_cfg: Any, note: str) -> Any:
    cfg = copy.deepcopy(hv_cfg)
    brain = cfg.setdefault("brain", {})
    brain["persona"] = f"{brain.get('persona') or ''}\n\n{note}".strip()
    return cfg


def make_brain(mode: str, hv_cfg: Any, listen: Callable[[], str], settings: Any) -> Brain:
    """A new brain for one device.

    Raises:
        BackendUnavailable: the mode is unknown, or the configured brain cannot serve it.
    """
    from halvoice.brains import BrainUnavailable
    from halvoice.brains import make_brain as hv_make_brain

    try:
        if mode == "desk":
            brain = hv_make_brain(hv_cfg)
        elif mode == "personal":
            brain = _personal_brain(hv_cfg, settings)
        elif mode == "home":
            return HomeAssistantBrain(settings)
        else:
            raise BackendUnavailable(f"unknown mode '{mode}'")
    except BrainUnavailable as exc:
        raise BackendUnavailable(str(exc)) from exc
    if hasattr(brain, "listen"):
        brain.listen = listen
    return brain


def _personal_brain(hv_cfg: Any, settings: Any) -> Brain:
    brain_mode = str(hv_cfg.get("brain.mode", "hal"))
    if brain_mode not in PERSONAL_BRAINS:
        raise BackendUnavailable(
            f"personal mode cannot use brain.mode '{brain_mode}', which has the PC's full "
            f"access; use one of: {', '.join(PERSONAL_BRAINS)}"
        )
    cfg = _with_persona_note(hv_cfg, str(settings.get("modes.personal.persona_note") or ""))
    denied = frozenset(settings.get("modes.personal.denied_packs") or ())
    if brain_mode == "hal":
        return _pack_filtered_acp_brain(cfg, denied)
    from halvoice.brains.openai import OpenAIBrain

    return OpenAIBrain(cfg)


def denied_pack(params: dict, denied: frozenset[str]) -> str | None:
    """The pack of a permission request when it is one of `denied`, else None.

    Hal titles a tool call `name [tier] pack`; a title in another shape is not refused here.
    """
    title = str((params.get("toolCall") or {}).get("title") or "")
    match = TOOL_TITLE.match(title)
    pack = match.group(2) if match else None
    return pack if pack in denied else None


def _pack_filtered_acp_brain(hv_cfg: Any, denied: frozenset[str]) -> Brain:
    # The subclass is defined here so this module imports without hal-voice installed
    from halvoice.brains.acp import AcpBrain

    class PackFilteredAcpBrain(AcpBrain):
        """hal-voice's ACP brain that refuses approval requests from denied packs."""

        def _answer_permission(self, msg: dict, speak: bool) -> str:
            if denied_pack(msg.get("params") or {}, denied):
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "result": {"outcome": {"outcome": "cancelled"}},
                    }
                )
                return ""
            return super()._answer_permission(msg, speak)

    return PackFilteredAcpBrain(hv_cfg)


def describe(mode: str) -> str:
    """One line for `hal-echo devices`."""
    return {
        "desk": "the desk: hal-voice's brain with all its tools",
        "personal": "a private room: no desktop tools",
        "home": "a shared room: Home Assistant only (stub)",
    }[mode]
