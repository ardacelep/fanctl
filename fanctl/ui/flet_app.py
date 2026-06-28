"""Flet frontend — runs as a desktop app or in the browser from one codebase.

Flet is async-native, so there is NO thread bridge: the backend's coroutines run
directly on Flet's event loop and ``on_change`` updates the UI in place.
"""

from __future__ import annotations

import flet as ft

from ..backend import DEFAULT_REGION, REGIONS, FanController, FanState

# ── Palette ──────────────────────────────────────────────────────────────────
BG     = "#1b1d24"
CARD   = "#262935"
CARD2  = "#2f3342"
ACCENT = "#5b8def"
GREEN  = "#3ecf8e"
RED    = "#f0616d"
TEXT   = "#e6e8ef"
SUBTLE = "#8b8fa3"

MODE_LABELS = {"normal": "Normal", "turbo": "Turbo", "auto": "Auto", "sleep": "Sleep"}


class FletApp:
    def __init__(self, page: ft.Page, controller: FanController):
        self.page = page
        self.ctrl = controller
        self.state = FanState()
        self.screen = "loading"
        self.busy = 0

        page.title = "fanctl"
        page.bgcolor = BG
        page.padding = 0
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER
        try:
            page.window.width = 400
            page.window.height = 720
            page.window.resizable = False
        except Exception:
            pass

        # Backend runs on Flet's own loop → listener can update the UI directly.
        self.ctrl.on_change(self._on_state)

    # ── Lifecycle / routing ────────────────────────────────────────────────

    async def start(self):
        self._show_loading("Connecting…")
        try:
            connected = await self.ctrl.restore_and_connect()
        except Exception:
            connected = False
        self._show_fan() if connected else self._show_login()

    def _swap(self, *controls):
        self.page.clean()
        self.page.add(*controls)
        self.page.update()

    # ── Loading ──────────────────────────────────────────────────────────────

    def _show_loading(self, msg: str):
        self.screen = "loading"
        self._swap(
            ft.Column(
                [
                    ft.Text("fanctl", size=26, weight=ft.FontWeight.BOLD, color=TEXT),
                    ft.ProgressRing(width=26, height=26, color=ACCENT),
                    ft.Text(msg, size=13, color=SUBTLE),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16, expand=True,
            )
        )

    # ── Login ────────────────────────────────────────────────────────────────

    def _show_login(self):
        self.screen = "login"
        self.in_email = ft.TextField(label="Email", width=300, border_color=CARD2,
                                     bgcolor=CARD, color=TEXT, on_submit=self._do_login)
        self.in_pass = ft.TextField(label="Password", width=300, password=True,
                                    can_reveal_password=True, border_color=CARD2,
                                    bgcolor=CARD, color=TEXT, on_submit=self._do_login)
        self.in_region = ft.Dropdown(
            label="Region", width=300, value=DEFAULT_REGION,
            options=[ft.dropdown.Option(r) for r in REGIONS],
            bgcolor=CARD, color=TEXT, border_color=CARD2,
        )
        self.btn_login = ft.FilledButton("Sign In", width=300, height=46,
                                         on_click=self._do_login,
                                         style=ft.ButtonStyle(bgcolor=ACCENT, color="#0b1733"))
        self.lbl_login_msg = ft.Text("", size=12, color=RED, width=300)

        self._swap(
            ft.Column(
                [
                    ft.Text("fanctl", size=28, weight=ft.FontWeight.BOLD, color=TEXT),
                    ft.Text("Sign in with your VeSync account", size=13, color=SUBTLE),
                    ft.Container(height=10),
                    self.in_email, self.in_pass, self.in_region,
                    ft.Container(height=4),
                    self.btn_login, self.lbl_login_msg,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12, expand=True,
            )
        )

    async def _do_login(self, e):
        email = (self.in_email.value or "").strip()
        pwd = self.in_pass.value or ""
        region = self.in_region.value or DEFAULT_REGION
        if not email or not pwd:
            self.lbl_login_msg.value = "Email and password required."
            self.page.update()
            return
        self.btn_login.text = "Signing in…"
        self.btn_login.disabled = True
        self.lbl_login_msg.value = ""
        self.page.update()
        try:
            await self.ctrl.login_and_connect(email, pwd, region)
            self._show_fan()
        except Exception as err:
            self.btn_login.text = "Sign In"
            self.btn_login.disabled = False
            self.lbl_login_msg.value = self._friendly_error(err)
            self.page.update()

    @staticmethod
    def _friendly_error(err: BaseException) -> str:
        name = err.__class__.__name__
        if "Login" in name:
            return "Wrong email or password."
        if "Server" in name or "Response" in name:
            return "Couldn't reach the server. Check your internet connection."
        return str(err) or name

    # ── Fan ──────────────────────────────────────────────────────────────────

    def _card(self, *controls, pad=16):
        return ft.Container(
            content=ft.Column(list(controls), spacing=10,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor=CARD, border_radius=16, padding=pad, width=344,
        )

    def _show_fan(self):
        self.screen = "fan"
        self.busy = 0

        self.lbl_status = ft.Text("Connected", size=13, color=GREEN)
        self.bar = ft.ProgressBar(color=ACCENT, bgcolor=CARD, visible=False)
        self.lbl_temp = ft.Text("–", size=52, weight=ft.FontWeight.BOLD, color=ACCENT)

        self.btn_power = ft.FilledButton("OFF", width=344, height=52,
                                         on_click=self._on_power)
        self.lbl_speed = ft.Text("–", size=15, weight=ft.FontWeight.BOLD, color=TEXT)
        self.sld = ft.Slider(min=1, max=12, divisions=11, active_color=ACCENT,
                             on_change=self._on_speed_move, on_change_end=self._on_speed_commit)

        self.seg = ft.SegmentedButton(
            segments=[ft.Segment(value=k, label=ft.Text(v, size=12))
                      for k, v in MODE_LABELS.items()],
            selected=["normal"], allow_multiple_selection=False,
            show_selected_icon=False,
            on_change=self._on_mode,
        )

        self.sw_osc = ft.Switch(value=False, active_color=GREEN, on_change=self._on_osc)
        self.sw_mute = ft.Switch(value=False, active_color=GREEN, on_change=self._on_mute)
        self.sw_disp = ft.Switch(value=False, active_color=GREEN, on_change=self._on_disp)

        def row(label, sw):
            return ft.Row([ft.Text(label, size=14, color=TEXT), sw],
                          alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        header = ft.Row(
            [ft.Text("fanctl", size=22, weight=ft.FontWeight.BOLD, color=TEXT),
             self.lbl_status],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=344,
        )
        footer = ft.Row(
            [ft.TextButton("↺ Refresh", on_click=self._on_refresh),
             ft.TextButton("Sign Out", on_click=self._do_logout)],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=344,
        )

        self._swap(
            ft.Column(
                [
                    ft.Container(height=10),
                    header,
                    self.bar,
                    self._card(
                        ft.Text("ROOM TEMPERATURE", size=11, weight=ft.FontWeight.BOLD, color=SUBTLE),
                        ft.Row([self.lbl_temp, ft.Text("°C", size=18, color=SUBTLE)],
                               alignment=ft.MainAxisAlignment.CENTER,
                               vertical_alignment=ft.CrossAxisAlignment.START),
                    ),
                    self.btn_power,
                    self._card(
                        ft.Row([ft.Text("Speed", size=13, color=SUBTLE), self.lbl_speed],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        self.sld,
                    ),
                    self._card(
                        ft.Text("MODE", size=11, weight=ft.FontWeight.BOLD, color=SUBTLE),
                        self.seg,
                    ),
                    self._card(row("Oscillation", self.sw_osc),
                               row("Mute", self.sw_mute),
                               row("Display", self.sw_disp)),
                    footer,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12, scroll=ft.ScrollMode.AUTO, expand=True,
            )
        )
        self._render(self.ctrl.state)
        self.page.update()      # push the initial state to the client

    # ── State → UI ────────────────────────────────────────────────────────────

    def _on_state(self, st: FanState):
        self._render(st)
        self.page.update()

    def _render(self, st: FanState):
        self.state = st
        if self.screen != "fan":
            return
        self.btn_power.text = "ON" if st.on else "OFF"
        self.btn_power.style = ft.ButtonStyle(
            bgcolor=GREEN if st.on else CARD2, color="#10241b" if st.on else TEXT)
        if st.speed:
            self.sld.value = st.speed          # programmatic set does NOT fire on_change_end
            self.lbl_speed.value = str(st.speed)
        if st.mode in MODE_LABELS:
            self.seg.selected = [st.mode]
        self.sw_osc.value = st.oscillation     # programmatic set does NOT fire on_change
        self.sw_mute.value = st.mute
        self.sw_disp.value = st.display
        self.lbl_temp.value = (f"{st.temperature_c:.1f}"
                               if st.temperature_c is not None else "–")

    # ── Syncing indicator ─────────────────────────────────────────────────────

    def _begin_busy(self):
        self.busy += 1
        if self.busy == 1:
            self.lbl_status.value = "Updating…"
            self.lbl_status.color = ACCENT
            self.bar.visible = True
            self.page.update()

    def _end_busy(self):
        self.busy = max(0, self.busy - 1)
        if self.busy == 0:
            self.lbl_status.value = "Connected"
            self.lbl_status.color = GREEN
            self.bar.visible = False
            self.page.update()

    async def _command(self, coro):
        self._begin_busy()
        try:
            await coro
        finally:
            self._end_busy()

    # ── Controls ─────────────────────────────────────────────────────────────

    async def _on_power(self, e):
        await self._command(self.ctrl.set_power(not self.state.on))

    def _on_speed_move(self, e):
        self.lbl_speed.value = str(int(e.control.value))
        self.page.update()

    async def _on_speed_commit(self, e):
        await self._command(self.ctrl.set_speed(int(e.control.value)))

    async def _on_mode(self, e):
        await self._command(self.ctrl.set_mode(e.control.selected[0]))

    async def _on_osc(self, e):
        await self._command(self.ctrl.set_oscillation(bool(e.control.value)))

    async def _on_mute(self, e):
        await self._command(self.ctrl.set_mute(bool(e.control.value)))

    async def _on_disp(self, e):
        await self._command(self.ctrl.set_display(bool(e.control.value)))

    async def _on_refresh(self, e):
        await self._command(self.ctrl.refresh())

    async def _do_logout(self, e):
        self._show_loading("Signing out…")
        await self.ctrl.logout()
        self._show_login()


def run(controller: FanController, web: bool = False):
    """Launch the Flet frontend (desktop by default, browser if web=True)."""
    async def main(page: ft.Page):
        await FletApp(page, controller).start()

    view = ft.AppView.WEB_BROWSER if web else ft.AppView.FLET_APP
    ft.run(main, view=view)
