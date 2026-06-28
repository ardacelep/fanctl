"""In-memory fake backend — same contract, no hardware/network.

Use it for hardware-free development, demos, and tests. It reuses the base
controller's lock/reconcile/generation logic, so it behaves identically to the
real device (including the reconcile delay), simulates mode side-effects on speed
(turbo→12, sleep→1, auto→4), and adds a little latency so the syncing indicator
is visible.

Fake auth lets the full login flow be exercised: ``_restore`` returns False (the
login screen shows), any non-empty credentials succeed, and the password
``"wrong"`` fails.
"""

from __future__ import annotations

import asyncio

from .controller import FanController
from .state import FanState

LATENCY = 0.25


class FakeFanController(FanController):
    def __init__(self):
        super().__init__()
        self._on = True
        self._speed = 6
        self._mode = "normal"
        self._osc = True
        self._mute = False
        self._disp = True
        self._temp_c = 27.5

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
        pass

    # ── Device (faked) ────────────────────────────────────────────────────

    def _snapshot(self) -> FanState:
        return FanState(
            on=self._on, speed=self._speed, mode=self._mode,
            oscillation=self._osc, mute=self._mute, display=self._disp,
            temperature_c=self._temp_c,
        )

    async def _pull(self) -> FanState:
        await asyncio.sleep(LATENCY)
        return self._snapshot()

    async def _apply_power(self, on: bool) -> None:
        await asyncio.sleep(LATENCY)
        self._on = on

    async def _apply_speed(self, n: int) -> None:
        await asyncio.sleep(LATENCY)
        self._speed = n
        self._mode = "normal"

    async def _apply_mode(self, mode: str) -> None:
        await asyncio.sleep(LATENCY)
        self._mode = mode
        self._speed = {"turbo": 12, "sleep": 1, "auto": 4}.get(mode, self._speed)

    async def _apply_toggle(self, kind: str, on: bool) -> None:
        await asyncio.sleep(LATENCY)
        setattr(self, {"oscillation": "_osc", "mute": "_mute", "display": "_disp"}[kind], on)
