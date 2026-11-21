"""Integration tests inside Home Assistant's own test harness."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

DOMAIN = "duskylights"
LIGHT = "light.test_lamp"


def set_sun(hass: HomeAssistant, elevation: float, rising: bool = False) -> None:
    hass.states.async_set(
        "sun.sun",
        "above_horizon" if elevation > 0 else "below_horizon",
        {"elevation": elevation, "rising": rising},
    )


def set_light(hass: HomeAssistant, on: bool, brightness: int | None = None) -> None:
    hass.states.async_set(
        LIGHT,
        "on" if on else "off",
        {"brightness": brightness} if on else {},
    )


async def setup(hass: HomeAssistant, elevation: float = 30.0, brightness: int = 128):
    set_sun(hass, elevation)
    set_light(hass, True, brightness)
    calls = async_mock_service(hass, "light", "turn_on")
    entry = MockConfigEntry(domain=DOMAIN, options={"lights": [LIGHT]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


def entity(hass: HomeAssistant, entry, unique_suffix: str) -> str:
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id(
        None, DOMAIN, f"{entry.entry_id}_{unique_suffix}"
    ) or next(
        e.entity_id
        for e in reg.entities.values()
        if e.unique_id == f"{entry.entry_id}_{unique_suffix}"
    )
    return eid


async def teardown(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


# The Sun integration (our dependency) leaves its own polling timer when set up
# for real, so this one test lets timers linger.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"lights": [LIGHT]}
    )
    assert result["type"] == "create_entry"
    assert result["options"] == {"lights": [LIGHT]}
    await hass.async_block_till_done()  # the entry sets itself up in the background
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await teardown(hass, entry)


async def test_only_one_instance(hass: HomeAssistant) -> None:
    entry, _ = await setup(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "abort"
    await teardown(hass, entry)


async def test_entities_and_defaults(hass: HomeAssistant) -> None:
    entry, _ = await setup(hass)
    normal = hass.states.get(entity(hass, entry, "normal_pct"))
    assert float(normal.state) == 50
    assert float(hass.states.get(entity(hass, entry, "floor_pct")).state) == 10
    assert float(hass.states.get(entity(hass, entry, "start_elevation")).state) == 10
    target = hass.states.get(entity(hass, entry, f"{LIGHT}_target"))
    assert float(target.state) == 50.0
    assert target.attributes["holding"] is False
    await teardown(hass, entry)


async def test_daytime_leaves_light_alone(hass: HomeAssistant) -> None:
    entry, calls = await setup(hass, elevation=30)
    assert calls == []
    await teardown(hass, entry)


async def test_dusk_dims_the_light(hass: HomeAssistant) -> None:
    entry, calls = await setup(hass)
    set_sun(hass, 2.0)  # halfway through the +10..-6 window: 30 %
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == LIGHT
    assert abs(calls[0].data["brightness"] - 77) <= 1
    assert calls[0].data["transition"] == 2.0
    target = hass.states.get(entity(hass, entry, f"{LIGHT}_target"))
    assert float(target.state) == 30.0
    await teardown(hass, entry)


async def test_manual_dim_holds_then_sun_catches_down(hass: HomeAssistant) -> None:
    entry, calls = await setup(hass)
    set_light(hass, True, 60)  # user dims 128 -> 60
    await hass.async_block_till_done()
    target = hass.states.get(entity(hass, entry, f"{LIGHT}_target"))
    assert target.attributes["holding"] is True
    assert target.attributes["hold_brightness"] == 60
    set_sun(hass, 6.0)  # ~44 % = 112 > 60: still held, nothing sent
    await hass.async_block_till_done()
    assert calls == []
    set_sun(hass, -3.0)  # ~13 % = 33 < 60: the sun owns it again
    await hass.async_block_till_done()
    assert len(calls) == 1 and calls[0].data["brightness"] < 60
    await teardown(hass, entry)


async def test_release_button_returns_to_curve(hass: HomeAssistant) -> None:
    entry, calls = await setup(hass)
    set_light(hass, True, 60)
    await hass.async_block_till_done()
    assert calls == []
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity(hass, entry, f"release_{LIGHT}")},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(calls) == 1 and calls[0].data["brightness"] == 128
    await teardown(hass, entry)


async def test_release_service_all(hass: HomeAssistant) -> None:
    entry, calls = await setup(hass)
    set_light(hass, True, 60)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "release", {}, blocking=True)
    await hass.async_block_till_done()
    assert len(calls) == 1 and calls[0].data["brightness"] == 128
    await teardown(hass, entry)


async def test_off_then_on_resets_hold_and_sets_target(hass: HomeAssistant) -> None:
    entry, calls = await setup(hass)
    set_light(hass, True, 60)
    set_light(hass, False)
    set_light(hass, True, 255)  # dimmer's own turn-on level
    await hass.async_block_till_done()
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(
        hass,
        dt_util.utcnow().replace(microsecond=0)
        + __import__("datetime").timedelta(seconds=2),
    )
    await hass.async_block_till_done()
    assert calls and calls[-1].data["brightness"] == 128
    await teardown(hass, entry)


async def test_per_light_override_beats_global(hass: HomeAssistant) -> None:
    entry, _ = await setup(hass)
    ov = entity(hass, entry, f"{LIGHT}_normal_override")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": ov, "value": 80}, blocking=True
    )
    await hass.async_block_till_done()
    target = hass.states.get(entity(hass, entry, f"{LIGHT}_target"))
    assert float(target.state) == 80.0
    await hass.services.async_call(
        "number", "set_value", {"entity_id": ov, "value": 0}, blocking=True
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(entity(hass, entry, f"{LIGHT}_target")).state) == 50.0
    await teardown(hass, entry)


async def test_global_setting_changes_target(hass: HomeAssistant) -> None:
    entry, _ = await setup(hass)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity(hass, entry, "normal_pct"), "value": 70},
        blocking=True,
    )
    await hass.async_block_till_done()
    target = hass.states.get(entity(hass, entry, f"{LIGHT}_target"))
    assert float(target.state) == 70.0
    await teardown(hass, entry)


async def test_demo_runs_one_light_and_stops(hass: HomeAssistant) -> None:
    entry, calls = await setup(hass)
    other = "light.other"
    hass.states.async_set(other, "on", {"brightness": 200})
    await hass.services.async_call(
        DOMAIN,
        "demo",
        {"entity_id": LIGHT, "duration": 0.5, "date": "2026-06-21", "start_hour": 12},
        blocking=True,
    )
    await hass.async_block_till_done()
    target = hass.states.get(entity(hass, entry, f"{LIGHT}_target"))
    assert target.attributes["demo"] is True
    assert calls[0].data["entity_id"] == LIGHT  # started the demo light
    assert all(c.data["entity_id"] == LIGHT for c in calls)  # never touched `other`
    await hass.services.async_call(DOMAIN, "demo_stop", {}, blocking=True)
    await hass.async_block_till_done()
    target = hass.states.get(entity(hass, entry, f"{LIGHT}_target"))
    assert target.attributes["demo"] is False
    await teardown(hass, entry)


async def test_demo_rejects_non_light(hass: HomeAssistant) -> None:
    import voluptuous as vol

    entry, _ = await setup(hass)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "demo", {"entity_id": "switch.nope"}, blocking=True
        )
    await teardown(hass, entry)


async def test_entity_ids_are_short(hass: HomeAssistant) -> None:
    entry, _ = await setup(hass)
    ids = {
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == entry.entry_id
    }
    assert {
        "number.dusky_high",
        "number.dusky_low",
        "number.dusky_start_elevation",
        "number.dusky_end_elevation",
        "number.dusky_start_sharpness",
        "number.dusky_end_sharpness",
        "number.dusky_test_lamp_high",
        "number.dusky_test_lamp_low",
        "button.dusky_release_all",
        "button.dusky_test_lamp_release",
        "sensor.dusky_test_lamp_target",
        "sensor.dusky_sun_elevation",
    } == ids
    await teardown(hass, entry)
