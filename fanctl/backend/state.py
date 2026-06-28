"""Frontend-facing data types and constants — no pyvesync types leak through."""

from __future__ import annotations

from dataclasses import dataclass

#: Fan operating modes (internal keys).
MODES = ("normal", "turbo", "auto", "sleep")

#: VeSync regions. "EU" is the Europe catch-all; the rest are their own regions.
#: The region is only a hint — VeSync auto-corrects a wrong choice at login via a
#: cross-region handshake (see ARCHITECTURE.md).
REGIONS = ("EU", "US", "CA", "MX", "JP")
DEFAULT_REGION = "EU"


@dataclass(frozen=True)
class FanState:
    """Immutable snapshot of the fan, handed to frontends via ``on_change``."""
    on: bool = False
    speed: int = 0                       # 1–12
    mode: str = ""                       # one of MODES
    oscillation: bool = False
    mute: bool = False
    display: bool = False
    temperature_c: float | None = None
