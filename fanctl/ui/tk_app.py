"""CustomTkinter frontend — alternative native desktop view.

This is a second frontend over the same backend.FanController, kept as a worked
example of how to plug a different UI onto the controller contract (see the Flet
frontend for the primary one). Unlike Flet, tkinter is synchronous, so this view
runs the async backend on its own event loop in a daemon thread and bridges with
``run_coroutine_threadsafe`` / ``root.after``.

Screens: loading splash → login (when no session) → fan.
"""

import asyncio
import threading
import time

import customtkinter as ctk

from ..backend import FanState, REGIONS, DEFAULT_REGION

# ── Palette ───────────────────────────────────────────────────────────────
BG       = "#1b1d24"
CARD     = "#262935"
CARD2    = "#2f3342"
ACCENT   = "#5b8def"
GREEN    = "#3ecf8e"
RED      = "#f0616d"
TEXT     = "#e6e8ef"
SUBTLE   = "#8b8fa3"

MODE_LABELS = {"Normal": "normal", "Turbo": "turbo", "Auto": "auto", "Sleep": "sleep"}
MODE_REV = {v: k for k, v in MODE_LABELS.items()}


class App:
    def __init__(self, controller):
        self._ctrl = controller
        self._state = FanState()
        self._screen = "loading"

        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title("fanctl")
        self.root.geometry("380x680")
        self.root.resizable(False, False)
        self.root.configure(fg_color=BG)

        # Asyncio event loop in a daemon thread — the bridge to the async backend.
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        self._last_action = 0.0
        self._busy = 0

        # Backend pushes state changes here (loop thread); marshal + render if on fan.
        self._ctrl.on_change(lambda st: self.root.after(0, lambda: self._render(st)))

        self.root.after(100, self._start)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Async bridge ──────────────────────────────────────────────────────

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _run(self, coro):
        """Run a command coroutine with the syncing indicator around it."""
        self._begin_busy()
        fut = self._submit(coro)
        fut.add_done_callback(lambda f: self._ui(self._end_busy))

    def _ui(self, fn):
        self.root.after(0, fn)

    def _mark_action(self):
        self._last_action = time.monotonic()

    def _clear_root(self):
        for w in self.root.winfo_children():
            w.destroy()

    # ── Startup / routing ─────────────────────────────────────────────────

    def _start(self):
        self._show_loading("Connecting…")
        fut = self._submit(self._ctrl.restore_and_connect())
        fut.add_done_callback(
            lambda f: self._ui(lambda: self._route(f.result() if not f.exception() else False)))

    def _route(self, connected: bool):
        self._show_fan() if connected else self._show_login()

    # ── Loading splash ────────────────────────────────────────────────────

    def _show_loading(self, msg: str):
        self._screen = "loading"
        self._clear_root()
        wrap = ctk.CTkFrame(self.root, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(wrap, text="fanctl", text_color=TEXT,
                     font=("SF Pro Display", 26, "bold")).pack(pady=(0, 14))
        bar = ctk.CTkProgressBar(wrap, mode="indeterminate", width=180,
                                 height=4, corner_radius=2, progress_color=ACCENT)
        bar.pack()
        bar.start()
        ctk.CTkLabel(wrap, text=msg, text_color=SUBTLE,
                     font=("SF Pro Text", 13)).pack(pady=(14, 0))

    # ── Login screen ──────────────────────────────────────────────────────

    def _show_login(self):
        self._screen = "login"
        self._clear_root()
        wrap = ctk.CTkFrame(self.root, fg_color="transparent", width=300)
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(wrap, text="fanctl", text_color=TEXT,
                     font=("SF Pro Display", 28, "bold")).pack()
        ctk.CTkLabel(wrap, text="Sign in with your VeSync account", text_color=SUBTLE,
                     font=("SF Pro Text", 13)).pack(pady=(2, 22))

        self.in_email = ctk.CTkEntry(wrap, width=280, height=42, corner_radius=10,
                                     placeholder_text="Email", fg_color=CARD,
                                     border_color=CARD2, font=("SF Pro Text", 13))
        self.in_email.pack(pady=6)
        self.in_pass = ctk.CTkEntry(wrap, width=280, height=42, corner_radius=10,
                                    placeholder_text="Password", show="•", fg_color=CARD,
                                    border_color=CARD2, font=("SF Pro Text", 13))
        self.in_pass.pack(pady=6)

        self.in_region = ctk.CTkOptionMenu(wrap, width=280, height=42, corner_radius=10,
                                           values=list(REGIONS), fg_color=CARD,
                                           button_color=CARD2, button_hover_color=ACCENT,
                                           font=("SF Pro Text", 13))
        self.in_region.set(DEFAULT_REGION)
        self.in_region.pack(pady=6)

        self.btn_login = ctk.CTkButton(wrap, text="Sign In", width=280, height=44,
                                       corner_radius=10, fg_color=ACCENT,
                                       hover_color="#4a7ad8", text_color="#0b1733",
                                       font=("SF Pro Text", 15, "bold"),
                                       command=self._do_login)
        self.btn_login.pack(pady=(14, 6))

        self.lbl_login_msg = ctk.CTkLabel(wrap, text="", text_color=RED,
                                          font=("SF Pro Text", 12), wraplength=280)
        self.lbl_login_msg.pack(pady=(2, 0))

        self.in_pass.bind("<Return>", lambda e: self._do_login())
        self.in_email.bind("<Return>", lambda e: self.in_pass.focus())
        self.in_email.focus()

    def _do_login(self):
        email = self.in_email.get().strip()
        pwd = self.in_pass.get()
        region = self.in_region.get()
        if not email or not pwd:
            self.lbl_login_msg.configure(text="Email and password required.")
            return
        self._login_form_enabled(False)
        self.btn_login.configure(text="Signing in…")
        self.lbl_login_msg.configure(text="")
        fut = self._submit(self._ctrl.login_and_connect(email, pwd, region))
        fut.add_done_callback(lambda f: self._ui(lambda: self._login_done(f.exception())))

    def _login_done(self, err: BaseException | None):
        if err is None:
            self._show_fan()
            return
        self._login_form_enabled(True)
        self.btn_login.configure(text="Sign In")
        self.lbl_login_msg.configure(text=self._friendly_error(err))

    def _login_form_enabled(self, on: bool):
        state = "normal" if on else "disabled"
        for w in (self.in_email, self.in_pass, self.in_region, self.btn_login):
            w.configure(state=state)

    @staticmethod
    def _friendly_error(err: BaseException) -> str:
        name = err.__class__.__name__
        if "Login" in name:
            return "Wrong email or password."
        if "Server" in name or "Response" in name:
            return "Couldn't reach the server. Check your internet connection."
        return str(err) or name

    # ── Fan screen ────────────────────────────────────────────────────────

    def _show_fan(self):
        self._screen = "fan"
        self._busy = 0
        self._clear_root()

        hdr = ctk.CTkFrame(self.root, fg_color="transparent")
        hdr.pack(fill="x", padx=22, pady=(22, 6))
        ctk.CTkLabel(hdr, text="fanctl", text_color=TEXT,
                     font=("SF Pro Display", 24, "bold")).pack(side="left")
        self.lbl_status = ctk.CTkLabel(hdr, text="Connected", text_color=GREEN,
                                       font=("SF Pro Text", 13))
        self.lbl_status.pack(side="right", pady=(8, 0))

        self.progress = ctk.CTkProgressBar(self.root, mode="indeterminate",
                                           height=4, corner_radius=2, progress_color=ACCENT)
        # Packed only while syncing (see _begin_busy); reserve nothing for now.

        # Temperature
        tcard = self._tcard = self._card(pady=(6, 0))
        ctk.CTkLabel(tcard, text="ROOM TEMPERATURE", text_color=SUBTLE,
                     font=("SF Pro Text", 11, "bold")).pack(pady=(16, 0))
        trow = ctk.CTkFrame(tcard, fg_color="transparent")
        trow.pack(pady=(0, 16))
        self.lbl_temp = ctk.CTkLabel(trow, text="–", text_color=ACCENT,
                                     font=("SF Pro Display", 52, "bold"))
        self.lbl_temp.pack(side="left")
        ctk.CTkLabel(trow, text="°C", text_color=SUBTLE,
                     font=("SF Pro Display", 20)).pack(side="left", anchor="n", pady=(12, 0))

        # Power
        self.btn_power = ctk.CTkButton(
            self.root, text="OFF", height=52, corner_radius=14,
            font=("SF Pro Text", 16, "bold"), fg_color=CARD2,
            hover_color=CARD2, command=self._on_power)
        self.btn_power.pack(fill="x", padx=18, pady=14)

        # Speed
        scard = self._card()
        srow = ctk.CTkFrame(scard, fg_color="transparent")
        srow.pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(srow, text="Speed", text_color=SUBTLE,
                     font=("SF Pro Text", 13)).pack(side="left")
        self.lbl_speed = ctk.CTkLabel(srow, text="–", text_color=TEXT,
                                      font=("SF Pro Text", 15, "bold"))
        self.lbl_speed.pack(side="right")
        self.slider = ctk.CTkSlider(
            scard, from_=1, to=12, number_of_steps=11,
            button_color=ACCENT, button_hover_color=ACCENT, progress_color=ACCENT,
            command=self._on_speed_move)
        self.slider.bind("<ButtonRelease-1>", self._on_speed_commit)
        self.slider.pack(fill="x", padx=18, pady=(0, 18))

        # Mode
        mcard = self._card()
        ctk.CTkLabel(mcard, text="MODE", text_color=SUBTLE,
                     font=("SF Pro Text", 11, "bold")).pack(anchor="w", padx=18, pady=(14, 6))
        self.seg_mode = ctk.CTkSegmentedButton(
            mcard, values=list(MODE_LABELS.keys()),
            selected_color=ACCENT, selected_hover_color=ACCENT,
            font=("SF Pro Text", 13), command=self._on_mode)
        self.seg_mode.pack(fill="x", padx=18, pady=(0, 18))

        # Toggles
        gcard = self._card()
        self.sw_osc  = self._switch_row(gcard, "Oscillation", "oscillation")
        self.sw_mute = self._switch_row(gcard, "Mute", "mute")
        self.sw_disp = self._switch_row(gcard, "Display", "display", last=True)

        # Footer: refresh + logout
        foot = ctk.CTkFrame(self.root, fg_color="transparent")
        foot.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkButton(foot, text="↺  Refresh", height=34, corner_radius=10,
                      fg_color="transparent", hover_color=CARD, text_color=SUBTLE,
                      font=("SF Pro Text", 12), command=self._on_refresh).pack(side="left")
        ctk.CTkButton(foot, text="Sign Out", height=34, corner_radius=10,
                      fg_color="transparent", hover_color=CARD, text_color=SUBTLE,
                      font=("SF Pro Text", 12), command=self._do_logout).pack(side="right")

        self._render(self._ctrl.state)
        self._schedule_auto_refresh()

    def _card(self, **kw) -> ctk.CTkFrame:
        f = ctk.CTkFrame(self.root, fg_color=CARD, corner_radius=16)
        f.pack(fill="x", padx=18, **kw)
        return f

    def _switch_row(self, parent, label, kind, last=False) -> ctk.CTkSwitch:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(16 if kind == "oscillation" else 8,
                                          16 if last else 0))
        ctk.CTkLabel(row, text=label, text_color=TEXT,
                     font=("SF Pro Text", 14)).pack(side="left")
        sw = ctk.CTkSwitch(row, text="", progress_color=GREEN, width=48)
        sw.configure(command=lambda k=kind, s=sw: self._on_switch(k, s))
        sw.pack(side="right")
        return sw

    # ── State → UI (one-way; programmatic widget updates never fire commands) ─

    def _render(self, st: FanState):
        self._state = st
        if self._screen != "fan":
            return

        self.btn_power.configure(
            text="ON" if st.on else "OFF",
            fg_color=GREEN if st.on else CARD2,
            hover_color=GREEN if st.on else CARD2,
            text_color="#10241b" if st.on else TEXT)

        if st.speed:
            self.slider.set(st.speed)
            self.lbl_speed.configure(text=str(st.speed))

        if st.mode in MODE_REV:
            self.seg_mode.set(MODE_REV[st.mode])

        self._set_switch(self.sw_osc,  st.oscillation)
        self._set_switch(self.sw_mute, st.mute)
        self._set_switch(self.sw_disp, st.display)

        self.lbl_temp.configure(
            text=f"{st.temperature_c:.1f}" if st.temperature_c is not None else "–")

    @staticmethod
    def _set_switch(sw: ctk.CTkSwitch, on: bool):
        sw.select() if on else sw.deselect()      # programmatic — no command fired

    def _set_status(self, text: str, color: str):
        self.lbl_status.configure(text=text, text_color=color)

    # ── Syncing indicator ─────────────────────────────────────────────────

    def _begin_busy(self):
        self._busy += 1
        if self._busy == 1:
            self._set_status("Updating…", ACCENT)
            self.progress.pack(fill="x", padx=22, pady=(0, 8), before=self._tcard)
            self.progress.start()

    def _end_busy(self):
        if self._screen != "fan":
            return
        self._busy = max(0, self._busy - 1)
        if self._busy == 0:
            self.progress.stop()
            self.progress.pack_forget()
            self._set_status("Connected", GREEN)

    # Poll the cloud so changes made elsewhere (VeSync app, the physical fan) show
    # up here. VeSync has no push API, so this is a poll.
    POLL_INTERVAL_MS = 10_000

    def _schedule_auto_refresh(self):
        def _tick():
            if self._screen != "fan":
                return                                  # stop loop after logout/close
            # Skip while a command/reconcile is running or just finished.
            if self._busy == 0 and time.monotonic() - self._last_action >= 5:
                self._submit(self._ctrl.refresh())      # silent background refresh
            self.root.after(self.POLL_INTERVAL_MS, _tick)
        self.root.after(self.POLL_INTERVAL_MS, _tick)

    # ── Controls ──────────────────────────────────────────────────────────

    def _on_power(self):
        self._mark_action()
        self._run(self._ctrl.set_power(not self._state.on))

    def _on_speed_move(self, value):
        self.lbl_speed.configure(text=str(int(value)))

    def _on_speed_commit(self, _event):
        self._mark_action()
        self._run(self._ctrl.set_speed(int(self.slider.get())))

    def _on_mode(self, label: str):
        self._mark_action()
        self._run(self._ctrl.set_mode(MODE_LABELS[label]))

    def _on_switch(self, kind: str, switch: ctk.CTkSwitch):
        self._mark_action()
        target = bool(switch.get())
        setter = {"oscillation": self._ctrl.set_oscillation,
                  "mute": self._ctrl.set_mute,
                  "display": self._ctrl.set_display}[kind]
        self._run(setter(target))

    def _on_refresh(self):
        self._mark_action()
        self._run(self._ctrl.refresh())

    def _do_logout(self):
        self._show_loading("Signing out…")
        fut = self._submit(self._ctrl.logout())
        fut.add_done_callback(lambda f: self._ui(self._show_login))

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def _on_close(self):
        self._submit(self._ctrl.close())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run(controller):
    """Launch the tkinter frontend with the given backend controller."""
    App(controller).run()
