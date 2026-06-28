"""In-memory fake backend — same contract, no hardware/network.

Use it for hardware-free development, demos, and tests. It reuses the base
controller's lock/reconcile/generation logic, so it behaves identically to the
real device (including the reconcile delay), simulates mode side-effects on speed
(turbo→12, sleep→1, auto→4), and adds a little latency so the syncing indicator
is visible.

It simulates a multi-device account: two controllable fans plus one unsupported
device, so the device-picker flow can be built and tested without hardware. Fake
auth lets the full login flow be exercised: any non-empty credentials succeed,
the password ``"wrong"`` fails, and ``_restore`` returns False (login shows).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .controller import FanController
from .state import DeviceInfo, FanState

LATENCY = 0.25


@dataclass
class _FakeFan:
    id: str
    name: str
    on: bool = True
    speed: int = 6
    mode: str = "normal"
    osc: bool = True
    mute: bool = False
    disp: bool = True
    temp_c: float = 27.5


class FakeFanController(FanController):
    def __init__(self):
        super().__init__()
        self._fans: dict[str, _FakeFan] = {
            "fan-living": _FakeFan("fan-living", "Living Room Fan", speed=6, mode="normal"),
            "fan-bedroom": _FakeFan("fan-bedroom", "Bedroom Fan", on=False, speed=3,
                                    mode="sleep", osc=False, temp_c=24.0),
        }
        # One unsupported device, to exercise the picker's "not supported" state.
        self._unsupported = [DeviceInfo(id="purifier-1", name="Air Purifier",
                                        kind="Purifier", supported=False)]
        self._active: _FakeFan | None = None

    # ── Auth (faked) ──────────────────────────────────────────────────────

    async def _authenticate(self, email: str, password: str, country_code: str) -> None:
        await asyncio.sleep(0.6)
        if not email or not password:
            raise ValueError("Email and password required")
        if password == "wrong":
            raise ValueError("Wrong email or password (demo)")

    async def _restore(self) -> bool:
        return False

    async def _logout(self) -> None:
        self._active = None

    # ── Devices (faked) ───────────────────────────────────────────────────

    async def _list_devices(self) -> list[DeviceInfo]:
        await asyncio.sleep(LATENCY)
        fans = [DeviceInfo(id=f.id, name=f.name, kind="Fan", supported=True)
                for f in self._fans.values()]
        out = fans + self._unsupported
        out.sort(key=lambda d: (not d.supported, d.name.lower()))
        return out

    async def _select(self, device_id: str) -> None:
        await asyncio.sleep(LATENCY)
        if device_id not in self._fans:
            raise RuntimeError("Device not found or not supported")
        self._active = self._fans[device_id]

    # ── Device (faked) ────────────────────────────────────────────────────

    def _snapshot(self) -> FanState:
        d = self._active
        return FanState(
            on=d.on, speed=d.speed, mode=d.mode,
            oscillation=d.osc, mute=d.mute, display=d.disp,
            temperature_c=d.temp_c,
        )

    async def _pull(self) -> FanState:
        await asyncio.sleep(LATENCY)
        return self._snapshot()

    async def _apply_power(self, on: bool) -> None:
        await asyncio.sleep(LATENCY)
        self._active.on = on

    async def _apply_speed(self, n: int) -> None:
        await asyncio.sleep(LATENCY)
        self._active.speed = n
        self._active.mode = "normal"

    async def _apply_mode(self, mode: str) -> None:
        await asyncio.sleep(LATENCY)
        self._active.mode = mode
        self._active.speed = {"turbo": 12, "sleep": 1, "auto": 4}.get(mode, self._active.speed)

    async def _apply_toggle(self, kind: str, on: bool) -> None:
        await asyncio.sleep(LATENCY)
        setattr(self._active, {"oscillation": "osc", "mute": "mute", "display": "disp"}[kind], on)
