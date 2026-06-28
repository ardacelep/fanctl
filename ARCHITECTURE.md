# Architecture

fanctl is split into a **UI-agnostic backend** (device + auth logic) and
**swappable frontends**. The whole point of the design is that a frontend never
needs to know anything about VeSync, threading, or cloud quirks — it only talks
to a small controller contract and renders immutable snapshots.

```
┌──────────────────────────────────────────────────────┐
│  fanctl/ui/   frontends (Flet, tkinter, …)            │
│  - render FanState snapshots                          │
│  - call controller methods on user input             │
└───────────────┬──────────────────────────────────────┘
                │  FanController contract (pure async)
┌───────────────▼──────────────────────────────────────┐
│  fanctl/backend/                                      │
│  state.py       FanState (immutable), MODES, REGIONS  │
│  controller.py  FanController (ABC) — the policy      │
│  vesync.py      VeSyncFanController (real device)     │
│  fake.py        FakeFanController (in-memory)         │
│  paths.py       cross-platform data dir (token)       │
└──────────────────────────────────────────────────────┘
```

## The controller contract

A frontend uses exactly this surface (`fanctl/backend/controller.py`):

```python
state -> FanState                       # current immutable snapshot
on_change(callback)                     # subscribe; called with FanState on every change

await restore_and_connect() -> bool     # True if a saved session connected
await login_and_connect(email, pw, cc)  # password login; persists a token; raises on failure
await logout()
await connect() / refresh()
await set_power(bool) / set_speed(int) / set_mode(str)
await set_oscillation(bool) / set_mute(bool) / set_display(bool)
await close()
```

`FanState` is a frozen dataclass: `on, speed, mode, oscillation, mute, display,
temperature_c`. No pyvesync types ever cross this boundary.

## Why it's shaped this way

### 1. One-way rendering (state → UI), never UI → command by accident
The single rule that keeps everything stable: **updating a widget
programmatically must never trigger a command.** Commands come only from genuine
user input. This is what lets background cloud refreshes update the UI freely
without creating feedback loops.

- Flet: `Slider.on_change_end` (commit on release); setting `.value`
  programmatically does not fire events.
- tkinter: speed commits on `<ButtonRelease-1>`; `CTkSlider.set()` /
  `CTkSwitch.select()` / `CTkSegmentedButton.set()` don't fire their commands.

### 2. Optimistic update → reconcile → generation guard
Every command runs this cycle in `FanController._command`:

1. **Optimistic** — send the command, update local state, emit immediately so the
   UI feels instant.
2. **Reconcile** — after `RECONCILE_DELAY` (1.5 s) pull *authoritative* state from
   the cloud and emit again. This catches server-side side-effects — e.g. Turbo
   mode makes the device pick speed 12; only a cloud read reveals it.
3. **Generation guard** — each command bumps a counter. A reconcile that wakes up
   to find the counter changed (a newer command arrived) **discards itself**, so a
   late, stale read can never overwrite fresher state.

All device I/O is serialized with an `asyncio.Lock` (VeSync dislikes concurrent
requests). A periodic background refresh is skipped for 20 s after any user
action so it can't clobber an optimistic update.

### 3. The dual-state-field gotcha
VeSync reports two values per toggle:

- `*_status` — the **transient actual** state (e.g. `screenState`, which flips
  when the screen auto-dims).
- `*_set_status` — the **commanded switch** (e.g. `screenSwitch`, what you set).

The UI binds to `*_set_status`. Binding to `*_status` made the display toggle look
flaky (command sent, beep heard, but the rendered state disagreed).

### 4. Token auth + cross-region
Login is two steps. The first hits a **global** endpoint and validates the
password regardless of region. The second exchanges for a token using the chosen
region; if the account lives elsewhere, VeSync returns a `CROSS_REGION` response
with the correct region and pyvesync **automatically retries**. So the region
picker is just a hint — a wrong choice still works (one extra round-trip).

Only the resulting **token** is persisted (never the password), via
`platformdirs` to the per-OS data dir (`paths.auth_file()`). Logout deletes it.

### 5. Temperature
The device reports Fahrenheit × 10; the backend converts once:
`°C = (raw/10 − 32) × 5/9`.

### 6. Async/threading is a *frontend* concern
The backend is pure async. How a frontend drives it differs:

- **Flet** is async-native → the controller runs on Flet's own loop, `on_change`
  updates the UI directly. **No threads.**
- **tkinter** is synchronous → it runs an asyncio loop in a daemon thread and
  bridges with `run_coroutine_threadsafe` / `root.after`.

This is exactly why the bridge lives in the UI layer and not the backend.

## Adding a new frontend

1. Construct a controller: `VeSyncFanController()` (or `FakeFanController()` for
   dev).
2. `controller.on_change(cb)` — in `cb`, copy fields from the `FanState` into your
   widgets. **Do not** call commands from here.
3. On user input, call the matching `await controller.set_*()` / `refresh()`.
4. Drive the coroutines however your toolkit prefers (native async, thread bridge,
   `asyncio.run`, …).
5. Wire it into `fanctl/__main__.py`.

A complete minimal frontend is just "subscribe + render + call set_*"; see
`fanctl/ui/tk_app.py` and `fanctl/ui/flet_app.py` as references.

## Adding a new device
`FanController` is the seam. A different VeSync device (another fan, a purifier)
means a new `*FanController` subclass implementing the device hooks
(`_pull`, `_snapshot`, `_apply_*`, auth hooks). The orchestration policy is
inherited unchanged.
