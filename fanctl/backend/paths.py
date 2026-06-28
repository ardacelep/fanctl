"""Cross-platform application data paths.

Uses platformdirs so the auth token lands in the right place on every OS:
  - macOS:   ~/Library/Application Support/fanctl/
  - Linux:   ~/.local/share/fanctl/
  - Windows: %LOCALAPPDATA%\\fanctl\\
"""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "fanctl"


def data_dir() -> Path:
    d = Path(user_data_dir(APP_NAME, appauthor=False))
    d.mkdir(parents=True, exist_ok=True)
    return d


def auth_file() -> Path:
    """Path to the persisted VeSync session token (no password is ever stored)."""
    return data_dir() / "auth.json"
