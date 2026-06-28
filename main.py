"""Entry point for `flet build` (packaged desktop / web / mobile bundles).

`flet build` runs this module by default (module name "main"). It launches the
Flet frontend with the real VeSync backend, so the packaged app opens straight
into the UI.

For development or the CLI, use the `fanctl` command instead (see README) —
that path also supports `--fake`, `--web`, and `--tk`.
"""

from fanctl.backend import VeSyncFanController
from fanctl.ui.flet_app import run

run(VeSyncFanController())
