"""The UI-agnostic controller contract and shared orchestration.

`FanController` owns the behaviour that every frontend relies on — the auth flow,
serialized device I/O, optimistic updates with a delayed cloud reconcile, and a
generation guard so stale reads never overwrite fresher state. It is pure async
with no UI or threading dependencies.

Frontends only ever:
  1. call the async methods (connect/login/set_*/refresh/logout), and
  2. subscribe with ``on_change(callback)`` to receive ``FanState`` snapshots.

Subclasses implement the small set of device/auth hooks at the bottom; the base
provides the policy, so the real and fake backends behave identically.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from .state import FanState

StateListener = Callable[[FanState], None]


class FanController(ABC):
    RECONCILE_DELAY = 1.5     # seconds to wait before pulling authoritative state

    def __init__(self):
        self._state = FanState()
        self._listeners: list[StateListener] = []
        self._lock = asyncio.Lock()
        self._gen = 0

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def state(self) -> FanState:
        return self._state

    def on_change(self, callback: StateListener) -> None:
        """Register a listener; called with a FanState whenever state changes."""
        self._listeners.append(callback)

    async def restore_and_connect(self) -> bool:
        """Try a saved session. True = logged in & connected; False = show login."""
        if not await self._restore():
            return False
        try:
            await self.connect()
            return True
        except Exception:
            await self._logout()             # token expired / invalid
            return False

    async def login_and_connect(self, email: str, password: str, country_code: str) -> None:
        """Authenticate with a password, persist the token, and connect.

        Raises on bad credentials / network errors so the UI can show them.
        """
        await self._authenticate(email, password, country_code)
        await self.connect()

    async def logout(self) -> None:
        await self._logout()
        self._state = FanState()

    async def connect(self) -> None:
        """Connect to the device (assumes already authenticated)."""
        async with self._lock:
            self._state = await self._pull()
        self._emit()

    async def refresh(self) -> None:
        gen = self._gen
        async with self._lock:
            new = await self._pull()
        if gen != self._gen:                 # a command landed mid-fetch; it's fresher
            return
        self._state = new
        self._emit()

    async def set_power(self, on: bool) -> None:
        await self._command(lambda: self._apply_power(on))

    async def set_speed(self, n: int) -> None:
        await self._command(lambda: self._apply_speed(n))

    async def set_mode(self, mode: str) -> None:
        await self._command(lambda: self._apply_mode(mode))

    async def set_oscillation(self, on: bool) -> None:
        await self._command(lambda: self._apply_toggle("oscillation", on))

    async def set_mute(self, on: bool) -> None:
        await self._command(lambda: self._apply_toggle("mute", on))

    async def set_display(self, on: bool) -> None:
        await self._command(lambda: self._apply_toggle("display", on))

    async def close(self) -> None:
        """Release resources (sessions etc.). Override if needed."""

    # ── Orchestration ─────────────────────────────────────────────────────

    async def _command(self, action: Callable[[], Awaitable[None]]) -> None:
        gen = self._bump()
        async with self._lock:
            await action()
            self._state = self._snapshot()   # optimistic: local state only
        self._emit()
        await self._reconcile(gen)

    async def _reconcile(self, gen: int, delay: float | None = None) -> None:
        await asyncio.sleep(self.RECONCILE_DELAY if delay is None else delay)
        if gen != self._gen:
            return
        async with self._lock:
            new = await self._pull()         # authoritative: catches side-effects
        if gen != self._gen:
            return
        self._state = new
        self._emit()

    def _bump(self) -> int:
        self._gen += 1
        return self._gen

    def _emit(self) -> None:
        for cb in self._listeners:
            cb(self._state)

    # ── Hooks (subclass implements) ───────────────────────────────────────

    @abstractmethod
    async def _authenticate(self, email: str, password: str, country_code: str) -> None: ...

    @abstractmethod
    async def _restore(self) -> bool:
        """Load a saved session if any. Return True if restored."""

    @abstractmethod
    async def _logout(self) -> None: ...

    @abstractmethod
    def _snapshot(self) -> FanState:
        """Build a FanState from local state — no network."""

    @abstractmethod
    async def _pull(self) -> FanState:
        """Refresh from the source of truth (cloud) and snapshot."""

    @abstractmethod
    async def _apply_power(self, on: bool) -> None: ...

    @abstractmethod
    async def _apply_speed(self, n: int) -> None: ...

    @abstractmethod
    async def _apply_mode(self, mode: str) -> None: ...

    @abstractmethod
    async def _apply_toggle(self, kind: str, on: bool) -> None: ...
