"""fanctl entry point.

    fanctl              # Flet desktop app (real fan)
    fanctl --web        # Flet app in the browser
    fanctl --tk         # alternative CustomTkinter desktop app
    fanctl --fake       # in-memory fake fan (no hardware) — combine with the above

Frontend and backend are chosen here and wired together; everything else is
frontend- and device-agnostic.
"""

from __future__ import annotations

import sys


def _make_controller(fake: bool):
    if fake:
        from .backend import FakeFanController
        return FakeFanController()
    from .backend import VeSyncFanController
    return VeSyncFanController()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if "-h" in args or "--help" in args:
        print(__doc__)
        return

    controller = _make_controller(fake="--fake" in args)

    if "--tk" in args:
        from .ui.tk_app import run
        run(controller)
    else:
        from .ui.flet_app import run
        run(controller, web="--web" in args)


if __name__ == "__main__":
    main()
