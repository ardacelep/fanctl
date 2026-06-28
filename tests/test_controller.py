"""Backend tests using the in-memory fake — no hardware or network needed.

These exercise the orchestration policy in FanController (optimistic update,
reconcile, generation guard), the auth flow, and the multi-device flow, all
through the public API.
"""

import asyncio

import pytest

from fanctl.backend import DeviceInfo, FakeFanController, FanState


@pytest.fixture
def fan():
    return FakeFanController()


async def _ready(fan, device_id="fan-living"):
    """Log in and select a device — the common precondition for control tests."""
    await fan.login("a@b.com", "secret", "EU")
    await fan.select(device_id)


async def test_restore_returns_false_without_session(fan):
    assert await fan.restore() is False


async def test_login_rejects_empty_and_wrong(fan):
    with pytest.raises(ValueError):
        await fan.login("", "", "EU")
    with pytest.raises(ValueError):
        await fan.login("a@b.com", "wrong", "EU")


async def test_list_devices_marks_supported(fan):
    await fan.login("a@b.com", "secret", "EU")
    devices = await fan.list_devices()
    assert all(isinstance(d, DeviceInfo) for d in devices)
    supported = [d for d in devices if d.supported]
    assert len(supported) == 2                 # two fake fans
    assert any(not d.supported for d in devices)  # plus an unsupported device


async def test_select_unsupported_raises(fan):
    await fan.login("a@b.com", "secret", "EU")
    with pytest.raises(Exception):
        await fan.select("purifier-1")


async def test_select_populates_state(fan):
    await _ready(fan, "fan-bedroom")
    assert isinstance(fan.state, FanState)
    assert fan.state.mode == "sleep"           # bedroom fan's initial mode


async def test_devices_are_independent(fan):
    await _ready(fan, "fan-living")
    await fan.set_mode("turbo")
    assert fan.state.speed == 12
    # switching to the other fan shows its own (unchanged) state
    await fan.select("fan-bedroom")
    assert fan.state.mode == "sleep"
    # and back: the living-room fan kept its turbo
    await fan.select("fan-living")
    assert fan.state.mode == "turbo"
    assert fan.state.speed == 12


async def test_mode_side_effect_on_speed(fan):
    await _ready(fan)
    await fan.set_mode("turbo")
    assert fan.state.mode == "turbo"
    assert fan.state.speed == 12


async def test_toggles_round_trip(fan):
    await _ready(fan)
    await fan.set_display(False)
    assert fan.state.display is False
    await fan.set_oscillation(False)
    assert fan.state.oscillation is False


async def test_on_change_emits_optimistic_then_authoritative(fan):
    await _ready(fan)
    seen = []
    fan.on_change(lambda st: seen.append(st.speed))
    await fan.set_mode("turbo")
    assert len(seen) >= 2                       # optimistic, then reconciled
    assert seen[-1] == 12


async def test_generation_guard_last_action_wins(fan):
    await _ready(fan)
    await asyncio.gather(fan.set_mode("sleep"), fan.set_mode("auto"))
    await asyncio.sleep(2)
    assert fan.state.mode == "auto"
    assert fan.state.speed == 4


async def test_logout_resets_state(fan):
    await _ready(fan)
    await fan.logout()
    assert fan.state == FanState()
