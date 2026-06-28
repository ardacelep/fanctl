"""fanctl backend — UI-agnostic device + auth logic.

Public surface:
    FanController   — abstract controller contract (subscribe via on_change)
    FanState        — immutable state snapshot
    VeSyncFanController, FakeFanController — concrete backends
    MODES, REGIONS, DEFAULT_REGION
"""

from .controller import FanController, StateListener
from .fake import FakeFanController
from .state import DEFAULT_REGION, MODES, REGIONS, DeviceInfo, FanState
from .vesync import VeSyncFanController

__all__ = [
    "FanController", "StateListener", "FanState", "DeviceInfo",
    "VeSyncFanController", "FakeFanController",
    "MODES", "REGIONS", "DEFAULT_REGION",
]
