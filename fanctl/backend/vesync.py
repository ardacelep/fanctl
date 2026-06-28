"""Real backend talking to a Levoit fan over the VeSync cloud (pyvesync v3).

Auth uses token persistence: the password is used once to log in, then only the
resulting token is stored (in the cross-platform data dir) — the password is
never saved. On the next launch the token is restored without a password.
"""

from __future__ import annotations

from pathlib import Path

from pyvesync import VeSync
from pyvesync.const import DeviceStatus

from .controller import FanController
from .paths import auth_file
from .state import DEFAULT_REGION, DeviceInfo, FanState


class VeSyncFanController(FanController):
    def __init__(self, auth_path: Path | None = None):
        super().__init__()
        self._auth_file = auth_path or auth_file()
        self._manager: VeSync | None = None
        self._fan = None

    # ── Auth ──────────────────────────────────────────────────────────────

    async def _authenticate(self, email: str, password: str, country_code: str) -> None:
        self._manager = VeSync(email, password, country_code=country_code)
        await self._manager.login()                       # raises on bad creds/network
        self._auth_file.parent.mkdir(parents=True, exist_ok=True)
        await self._manager.auth.save_credentials_to_file(self._auth_file)

    async def _restore(self) -> bool:
        if not self._auth_file.exists():
            return False
        mgr = VeSync("", "", country_code=DEFAULT_REGION)
        ok = await mgr.auth.load_credentials_from_file(self._auth_file)
        if ok:
            self._manager = mgr
        return ok

    async def _logout(self) -> None:
        if self._manager is not None:
            try:
                self._manager.auth.clear_credentials()
                await self._manager.__aexit__(None, None, None)
            except Exception:
                pass
            self._manager = None
        self._fan = None
        self._auth_file.unlink(missing_ok=True)

    # ── Devices ───────────────────────────────────────────────────────────

    async def _list_devices(self) -> list[DeviceInfo]:
        await self._manager.update()
        supported = {f.cid for f in self._manager.devices.fans}
        devices = [
            DeviceInfo(
                id=dev.cid,
                name=dev.device_name or dev.device_type,
                kind=(getattr(dev, "product_type", "") or "Fan") if dev.cid in supported
                     else (getattr(dev, "product_type", "") or dev.device_type or "Device"),
                supported=dev.cid in supported,
            )
            for dev in self._manager.devices
        ]
        devices.sort(key=lambda d: (not d.supported, d.name.lower()))
        return devices

    async def _select(self, device_id: str) -> None:
        if self._manager.devices.fans is None or not self._manager.devices.fans:
            await self._manager.update()
        for fan in self._manager.devices.fans:
            if fan.cid == device_id:
                self._fan = fan
                return
        raise RuntimeError("Device not found or not supported")

    # ── Device ────────────────────────────────────────────────────────────

    async def _pull(self) -> FanState:
        await self._manager.update()
        if self._fan is None:
            raise RuntimeError("No device selected")
        return self._snapshot()

    def _snapshot(self) -> FanState:
        s = self._fan.state
        temp = None
        if s.temperature is not None:
            temp = (s.temperature / 10.0 - 32) * 5 / 9    # device reports °F × 10
        return FanState(
            on=self._fan.is_on,
            speed=s.fan_level or 0,
            mode=s.mode or "",
            # Bind to the commanded switch (*_set_status), not the transient actual
            # state (*_status, e.g. screen auto-dim), so toggles stay stable.
            oscillation=s.oscillation_set_status == "on",
            mute=s.mute_set_status == "on",
            display=s.display_set_status == "on",
            temperature_c=temp,
        )

    async def _apply_power(self, on: bool) -> None:
        await (self._fan.turn_on() if on else self._fan.turn_off())

    async def _apply_speed(self, n: int) -> None:
        await self._fan.set_fan_speed(n)

    async def _apply_mode(self, mode: str) -> None:
        await {
            "normal": self._fan.set_normal_mode,
            "turbo":  self._fan.set_turbo_mode,
            "auto":   self._fan.set_auto_mode,
            "sleep":  self._fan.set_sleep_mode,
        }[mode]()

    async def _apply_toggle(self, kind: str, on: bool) -> None:
        method, set_attr = {
            "oscillation": ("toggle_oscillation", "oscillation_set_status"),
            "mute":        ("toggle_mute",        "mute_set_status"),
            "display":     ("toggle_display",     "display_set_status"),
        }[kind]
        await getattr(self._fan, method)(on)
        # toggle_* updates the *actual* field locally; mirror the commanded switch
        # too so the optimistic snapshot reflects the change before reconcile.
        setattr(self._fan.state, set_attr, DeviceStatus.from_bool(on))

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
