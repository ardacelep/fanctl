"""Backend tests using the in-memory fake — no hardware or network needed.

These exercise the orchestration policy in FanController (optimistic update,
reconcile, generation guard) plus the auth flow, all through the public API.
"""

import asyncio

import pytest

from fanctl.backend import FakeFanController, FanState


@pytest.fixture
def fan():
    return FakeFanController()


async def test_restore_returns_false_without_session(fan):
    assert await fan.restore_and_connect() is False


async def test_login_rejects_empty_and_wrong(fan):
    with pytest.raises(ValueError):
        await fan.login_and_connect("", "", "EU")
    with pytest.raises(ValueError):
        await fan.login_and_connect("a@b.com", "wrong", "EU")


async def test_login_then_state_populated(fan):
    await fan.login_and_connect("a@b.com", "secret", "EU")
    assert isinstance(fan.state, FanState)
    assert fan.state.on is True
    assert 1 <= fan.state.speed <= 12


async def test_mode_side_effect_on_speed(fan):
    await fan.login_and_connect("a@b.com", "secret", "EU")
    await fan.set_mode("turbo")
    assert fan.state.mode == "turbo"
    assert fan.state.speed == 12          # device chose the speed; reconcile caught it


async def test_toggles_round_trip(fan):
    await fan.login_and_connect("a@b.com", "secret", "EU")
    await fan.set_display(False)
    assert fan.state.display is False
    await fan.set_oscillation(False)
    assert fan.state.oscillation is False


async def test_on_change_emits_optimistic_then_authoritative(fan):
    await fan.login_and_connect("a@b.com", "secret", "EU")
    seen = []
    fan.on_change(lambda st: seen.append(st.speed))
    await fan.set_mode("turbo")
    # at least two emits: optimistic (old speed) then reconciled (12)
    assert len(seen) >= 2
    assert seen[-1] == 12


async def test_generation_guard_last_action_wins(fan):
    await fan.login_and_connect("a@b.com", "secret", "EU")
    # Fire two mode changes concurrently; the later one must win.
    await asyncio.gather(fan.set_mode("sleep"), fan.set_mode("auto"))
    await asyncio.sleep(2)                 # let any late reconcile settle
    assert fan.state.mode == "auto"
    assert fan.state.speed == 4


async def test_logout_resets_state(fan):
    await fan.login_and_connect("a@b.com", "secret", "EU")
    await fan.logout()
    assert fan.state == FanState()
