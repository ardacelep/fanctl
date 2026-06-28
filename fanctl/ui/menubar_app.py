"""macOS menu bar frontend (rumps) — control the fan from the status bar.

Another frontend over the same backend.FanController. rumps must run on the main
thread, so the async backend runs on an asyncio loop in a daemon thread (commands
are submitted with run_coroutine_threadsafe), and a rumps Timer on the main thread
renders the menu from `controller.state` — keeping all UI updates on the main thread.

Sign-in happens in the windowed app: if there's no saved session, the menu offers
to open it. Once a token exists, the menu bar restores it automatically.

macOS only. Install with: pip install "fanctl[menubar]"
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
from pathlib import Path

import rumps

from ..backend import DEFAULT_REGION, MODES, FanController, FanState  # noqa: F401

MODE_LABELS = {"normal": "Normal", "turbo": "Turbo", "auto": "Auto", "sleep": "Sleep"}
ICON = str(Path(__file__).parent / "assets" / "menubar_icon.png")


class MenuBarApp(rumps.App):
    def __init__(self, controller: FanController):
        # template=True lets macOS recolor the icon for light/dark menu bars.
        super().__init__("fanctl", title=None, icon=ICON, template=True, quit_button="Quit")
        self.ctrl = controller

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        self._authed = False
        self._restoring = False
        self._devices = []          # list[DeviceInfo]
        self._devices_built = False
        self._busy = 0

        # ── Build the (static) menu; the Timer fills in live values ──────────
        self.m_status = rumps.MenuItem("Connecting…")
        self.m_temp = rumps.MenuItem("Temperature: –")
        self.m_power = rumps.MenuItem("Power", callback=self._on_power)
        self.m_speed = [rumps.MenuItem(str(n), callback=self._on_speed) for n in range(1, 13)]
        self.m_mode = {k: rumps.MenuItem(v, callback=self._on_mode) for k, v in MODE_LABELS.items()}
        self.m_osc = rumps.MenuItem("Oscillation", callback=self._on_osc)
        self.m_mute = rumps.MenuItem("Mute", callback=self._on_mute)
        self.m_disp = rumps.MenuItem("Display", callback=self._on_disp)
        self.m_refresh = rumps.MenuItem("Refresh", callback=self._on_refresh)
        self.m_signin = rumps.MenuItem("Sign in…", callback=self._open_app)
        self.m_signout = rumps.MenuItem("Sign Out", callback=self._on_signout)

        self.menu = [
            self.m_status,
            self.m_temp,
            None,
            self.m_power,
            {"Speed": self.m_speed},
            {"Mode": list(self.m_mode.values())},
            None,
            self.m_osc, self.m_mute, self.m_disp,
            None,
            # A dict entry creates the submenu (with its NSMenu), so it can be
            # cleared/rebuilt later once the device list arrives.
            {"Devices": [rumps.MenuItem("Loading…")]},
            self.m_refresh,
            None,
            self.m_signin,
            self.m_signout,
        ]
        self.m_devices = self.menu["Devices"]

        self._submit(self._start())
        self._timer = rumps.Timer(self._sync, 3)
        self._timer.start()

    # ── async bridge ────────────────────────────────────────────────────────

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _run(self, coro):
        self._busy += 1
        fut = self._submit(coro)
        fut.add_done_callback(lambda f: setattr(self, "_busy", max(0, self._busy - 1)))

    # ── startup / data (asyncio thread) ──────────────────────────────────────

    async def _start(self):
        try:
            self._authed = await self.ctrl.restore()
        except Exception:
            self._authed = False
        if self._authed:
            await self._load_devices()

    async def _retry_restore(self):
        """Poll for a session created in the windowed app, then connect."""
        try:
            if await self.ctrl.restore():
                self._authed = True
                await self._load_devices()
        except Exception:
            pass
        finally:
            self._restoring = False

    async def _load_devices(self):
        try:
            self._devices = await self.ctrl.list_devices()
        except Exception:
            self._devices = []
            return
        self._devices_built = False
        supported = [d for d in self._devices if d.supported]
        if supported:
            try:
                await self.ctrl.select(supported[0].id)
            except Exception:
                pass

    # ── render (main thread, via Timer) ──────────────────────────────────────

    def _sync(self, _timer):
        if not self._authed:
            self.m_status.title = "Not signed in"
            self.m_temp.title = "Sign in to control your fan"
            self.m_signin.set_callback(self._open_app)
            self.m_signout.set_callback(None)
            # Auto-detect a sign-in done in the windowed app (token appears).
            if not self._restoring:
                self._restoring = True
                self._submit(self._retry_restore())
            return

        self.m_signin.set_callback(None)            # already signed in
        self.m_signout.set_callback(self._on_signout)
        self._build_devices_menu()

        st: FanState = self.ctrl.state
        self.m_status.title = ("Updating…" if self._busy else "Connected")
        self.m_temp.title = (f"Temperature: {st.temperature_c:.1f}°C"
                             if st.temperature_c is not None else "Temperature: –")
        self.m_power.title = "Power: On" if st.on else "Power: Off"
        self.m_power.state = 1 if st.on else 0
        for n, item in enumerate(self.m_speed, start=1):
            item.state = 1 if n == st.speed else 0
        for key, item in self.m_mode.items():
            item.state = 1 if key == st.mode else 0
        self.m_osc.state = 1 if st.oscillation else 0
        self.m_mute.state = 1 if st.mute else 0
        self.m_disp.state = 1 if st.display else 0

    def _build_devices_menu(self):
        if self._devices_built:
            return
        self.m_devices.clear()
        for dev in self._devices:
            title = dev.name if dev.supported else f"{dev.name} (unsupported)"
            item = rumps.MenuItem(title, callback=self._on_select_device if dev.supported else None)
            item.fanctl_id = dev.id
            self.m_devices.add(item)
        if not self._devices:
            self.m_devices.add(rumps.MenuItem("No devices"))
        self._devices_built = True

    # ── actions (main thread → submit to loop) ───────────────────────────────

    def _on_power(self, _s):
        self._run(self.ctrl.set_power(not self.ctrl.state.on))

    def _on_speed(self, sender):
        self._run(self.ctrl.set_speed(int(sender.title)))

    def _on_mode(self, sender):
        key = next(k for k, v in MODE_LABELS.items() if v == sender.title)
        self._run(self.ctrl.set_mode(key))

    def _on_osc(self, _s):
        self._run(self.ctrl.set_oscillation(not self.ctrl.state.oscillation))

    def _on_mute(self, _s):
        self._run(self.ctrl.set_mute(not self.ctrl.state.mute))

    def _on_disp(self, _s):
        self._run(self.ctrl.set_display(not self.ctrl.state.display))

    def _on_refresh(self, _s):
        self._run(self.ctrl.refresh())

    def _on_select_device(self, sender):
        self._run(self.ctrl.select(sender.fanctl_id))

    def _on_signout(self, _s):
        async def _do():
            await self.ctrl.logout()
            self._authed = False
            self._devices = []
            self._devices_built = False
        self._submit(_do())

    def _open_app(self, _s):
        # Sign-in is nicer in the windowed app; launch it, then we restore the token.
        subprocess.Popen([sys.executable, "-m", "fanctl"])


def run(controller: FanController):
    """Launch the macOS menu bar frontend (blocks on the main thread)."""
    MenuBarApp(controller).run()
