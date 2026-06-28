# Contributing to fanctl

Thanks for taking a look! fanctl is designed to be easy to hack on — the device
logic is isolated from the UI, and there's an in-memory fake backend so you can
develop and test **without a real fan or even an internet connection**.

Please read [ARCHITECTURE.md](ARCHITECTURE.md) first; it explains the controller
contract and the design rules (especially "one-way rendering").

## Dev setup

```bash
git clone https://github.com/ardacelep/fanctl
cd fanctl
python3 -m venv venv && source venv/bin/activate
pip install -e ".[tk,dev]"      # editable install + tkinter frontend + dev tools
```

> **tkinter note:** the `--tk` frontend needs Python built with Tcl/Tk. If
> `import tkinter` fails (common with pyenv), see the README's tkinter note. The
> default Flet frontend does not need Tk.

## Run

```bash
fanctl --fake              # Flet desktop, fake fan — no hardware needed
fanctl --fake --web        # same, in the browser
fanctl --fake --tk         # tkinter frontend, fake fan
fanctl                     # real fan (prompts login on first run)
```

(`python3 -m fanctl ...` works identically.)

## Tests

```bash
pytest
```

Tests run entirely against `FakeFanController` (no network), covering the
controller policy — optimistic update, reconcile, the generation guard, the auth
flow, and toggles. Add tests there when you change backend behavior.

## Lint

```bash
ruff check .
```

## Ways to contribute

- **A new frontend** — the most fun extension point. See "Adding a new frontend"
  in ARCHITECTURE.md. A frontend is just *subscribe + render + call `set_*`*.
- **A new device** — subclass `FanController` with the device hooks; the
  orchestration is inherited. See "Adding a new device" in ARCHITECTURE.md.
- **Bug fixes / polish** — please include a test using the fake backend where it
  makes sense.

## Conventions

- Keep the **backend UI-agnostic**: no UI or threading imports in `fanctl/backend/`.
- Keep **rendering one-way**: a frontend must never issue a command as a side
  effect of a programmatic widget update.
- No pyvesync types in `FanState` or across the controller boundary.
- Never commit credentials. `auth.json` / `config.json` are git-ignored; the app
  only ever persists a token, never a password.

## Pull requests

Small, focused PRs are easiest to review. Mention whether you tested against the
fake backend, a real device, or both.
