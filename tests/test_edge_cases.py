"""Edge cases a user would actually notice."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.duskylights.const import DOMAIN

from .test_integration import LIGHT, entity, set_light, set_sun, setup, teardown

CTRL = "custom_components.duskylights.controller"


async def run_demo(hass, light=LIGHT, **data):
    await hass.services.async_call(
        DOMAIN,
        "demo",
        {"entity_id": light, "date": "2026-06-21", **data},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_reload_or_unload_during_a_demo_puts_the_light_back(hass) -> None:
    entry, calls = await setup(hass, brightness=60)
    await run_demo(hass)
    calls.clear()
    await teardown(hass, entry)  # what an options change, update or reload does
    assert calls and calls[-1].data["brightness"] == 60


async def test_demo_on_an_unavailable_light_is_refused_and_leaves_a_running_demo(
    hass,
) -> None:
    entry, _ = await setup(hass)
    other = "light.gone"
    hass.states.async_set(other, "unavailable")
    await run_demo(hass)  # a demo is running on LIGHT
    with pytest.raises(ServiceValidationError):
        await run_demo(hass, light=other)
    assert entry.runtime_data.demo_light == LIGHT  # still going
    await teardown(hass, entry)


async def test_switching_the_demo_to_another_light_restores_the_first(hass) -> None:
    entry, calls = await setup(hass, brightness=60)
    hass.states.async_set("light.other", "on", {"brightness": 200})
    await run_demo(hass)
    calls.clear()
    await run_demo(hass, light="light.other")
    await hass.async_block_till_done()
    assert any(
        c.data["entity_id"] == LIGHT and c.data.get("brightness") == 60 for c in calls
    )
    assert entry.runtime_data.demo_light == "light.other"
    await teardown(hass, entry)


async def test_demo_finishing_by_itself_restores_the_light_and_switch_goes_off(
    hass,
) -> None:
    entry, calls = await setup(hass, brightness=60)
    c = entry.runtime_data
    await run_demo(hass)
    t = c.demo.started_at + c.demo.duration_s + 5
    calls.clear()
    with patch(f"{CTRL}.time.monotonic", return_value=t):
        c._tick()
        await hass.async_block_till_done()
    assert c.demo is None
    assert hass.states.get(entity(hass, entry, "demo")).state == "off"
    assert calls[-1].data["brightness"] == 60
    await teardown(hass, entry)


async def test_light_switched_off_during_a_demo_is_not_turned_back_on(hass) -> None:
    entry, calls = await setup(hass, brightness=60)
    c = entry.runtime_data
    await run_demo(hass)
    set_light(hass, False)
    await hass.async_block_till_done()
    calls.clear()
    with patch(f"{CTRL}.time.monotonic", return_value=c.demo.started_at + 3):
        c._tick()
        await hass.async_block_till_done()
    assert not calls
    await teardown(hass, entry)


async def test_demo_where_the_sun_never_sets_or_never_rises_does_not_break(
    hass,
) -> None:
    entry, _calls = await setup(hass, brightness=60)
    hass.config.latitude = 85.0  # midnight sun in June
    c = entry.runtime_data
    await run_demo(hass)
    started = c.demo.started_at
    for step in (0.5, 5, 15, 40):
        with patch(f"{CTRL}.time.monotonic", return_value=started + step):
            c._tick()
            await hass.async_block_till_done()
        assert c.demo is not None
    with patch(f"{CTRL}.time.monotonic", return_value=started + 500):
        c._tick()  # past the end: finishes cleanly
        await hass.async_block_till_done()
    assert c.demo is None
    await teardown(hass, entry)


async def test_start_not_above_end_elevation_does_not_break_the_demo_or_live(
    hass,
) -> None:
    entry, _calls = await setup(hass, elevation=0.0, brightness=100)
    c = entry.runtime_data
    c.set_value("start_elevation", -10)
    c.set_value("end_elevation", 5)  # window is upside down
    await hass.async_block_till_done()
    assert c.target_pct(LIGHT) == 50.0  # holds the normal level
    await run_demo(hass)
    assert c.demo is not None
    await teardown(hass, entry)


@pytest.mark.parametrize(
    "state, attrs",
    [
        ("unavailable", {}),
        ("unknown", {}),
        ("above_horizon", {}),
        ("x", {"elevation": "n/a"}),
    ],
)
async def test_sun_entity_misbehaving_changes_nothing(hass, state, attrs) -> None:
    entry, calls = await setup(hass, elevation=30.0, brightness=128)
    calls.clear()
    hass.states.async_set("sun.sun", state, attrs)
    await hass.async_block_till_done()
    assert not calls
    await teardown(hass, entry)


async def test_light_unavailable_then_back_is_handled(hass) -> None:
    entry, _calls = await setup(hass, elevation=-20.0, brightness=200)
    hass.states.async_set(LIGHT, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(LIGHT, "on", {"brightness": 200})
    await hass.async_block_till_done()
    await teardown(hass, entry)


async def test_removing_a_light_removes_its_entities_and_device(hass) -> None:
    hass.states.async_set("light.second", "on", {"brightness": 100})
    set_sun(hass, 30.0)
    set_light(hass, True, 128)
    async_mock_service(hass, "light", "turn_on")
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, options={"lights": [LIGHT, "light.second"]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)

    def mine():
        return [
            e.unique_id
            for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        ]

    assert any("light.second" in u for u in mine())
    hass.config_entries.async_update_entry(entry, options={"lights": [LIGHT]})
    await hass.config_entries.async_reload(entry.entry_id)  # what the options flow does
    await hass.async_block_till_done()
    assert not any("light.second" in u for u in mine())
    assert any(LIGHT in u for u in mine())
    assert not [
        d
        for d in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        if any("light.second" in i for _d, i in d.identifiers)
    ]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_choosing_no_lights_is_rejected(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"lights": []}
        )


async def test_bad_demo_input_over_the_panel_is_rejected_or_clamped(
    hass, hass_ws_client
) -> None:
    entry, _ = await setup(hass)
    c = entry.runtime_data
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/demo",
            "light": LIGHT,
            "preview": {"settings": {"normal_pct": "abc"}},
        }
    )
    assert not (await client.receive_json())["success"]
    await client.send_json({"id": 2, "type": f"{DOMAIN}/demo", "light": "switch.nope"})
    assert not (await client.receive_json())["success"]
    await client.send_json(
        {"id": 3, "type": f"{DOMAIN}/demo", "light": LIGHT, "seconds": 99999}
    )
    assert not (await client.receive_json())["success"]
    await client.send_json(
        {
            "id": 4,
            "type": f"{DOMAIN}/demo",
            "light": LIGHT,
            "preview": {
                "settings": {"normal_pct": 500, "bogus": 1, "sharp_start": -4},
                "overrides": {"floor": 900},
            },
        }
    )
    assert (await client.receive_json())["success"]
    assert c._demo_values["normal_pct"] == 100  # clamped to the entity's range
    assert c._demo_values["sharp_start"] == 0
    assert "bogus" not in c._demo_values
    assert c._demo_ov["floor"] == 100
    await teardown(hass, entry)


async def test_sun_path_covers_the_local_day_including_clock_change_days(
    hass, hass_ws_client, freezer
) -> None:
    entry, _ = await setup(hass)
    await hass.config.async_set_time_zone("America/Los_Angeles")
    client = await hass_ws_client(hass)
    for i, (day, hours) in enumerate(
        (("2026-06-21", 24), ("2026-03-08", 23), ("2026-11-01", 25)), 1
    ):
        freezer.move_to(f"{day} 20:00:00+00:00")  # midday in Los Angeles
        await client.send_json({"id": i, "type": f"{DOMAIN}/sun_path"})
        res = (await client.receive_json())["result"]
        assert len(res["elevations"]) == hours * 3600 // res["step_s"], day
        assert max(res["elevations"]) > 0 > min(res["elevations"])
    await teardown(hass, entry)


async def test_each_light_device_hangs_off_the_hub_device(hass) -> None:
    entry, _ = await setup(hass)
    reg = dr.async_get(hass)
    by_id = {
        i: d
        for d in dr.async_entries_for_config_entry(reg, entry.entry_id)
        for i in d.identifiers
    }
    hub = by_id[(DOMAIN, entry.entry_id)]
    child = by_id[(DOMAIN, f"{entry.entry_id}_{LIGHT}")]
    assert hub and child and child.via_device_id == hub.id


async def test_a_light_can_have_its_own_start_end_and_sharpness_and_go_back(
    hass,
) -> None:
    entry, _ = await setup(hass)
    c = entry.runtime_data
    start = entity(hass, entry, f"{LIGHT}_start_elevation_override")
    assert hass.states.get(start).state == "unknown"  # follows the global value
    base = c._pct(LIGHT, 5.0)

    await hass.services.async_call(
        "number", "set_value", {"entity_id": start, "value": 4.0}, blocking=True
    )
    assert base < c.values["normal_pct"]  # 5 degrees is inside the global window...
    assert (
        c._pct(LIGHT, 5.0) == c.values["normal_pct"]
    )  # ...but above this light's own start
    assert c.overrides[LIGHT]["start_elevation"] == 4.0
    # another setting on the same light is untouched
    assert c.effective(LIGHT)["end_elevation"] == c.values["end_elevation"]

    await hass.services.async_call(
        DOMAIN, "clear_override", {"entity_id": start}, blocking=True
    )
    assert hass.states.get(start).state == "unknown"
    assert "start_elevation" not in c.overrides[LIGHT]
    assert c._pct(LIGHT, 5.0) == base  # back to the global curve
    await teardown(hass, entry)


async def test_zero_is_a_real_override_for_elevations_and_clear_works_for_high_low(
    hass,
) -> None:
    entry, _ = await setup(hass)
    c = entry.runtime_data
    end = entity(hass, entry, f"{LIGHT}_end_elevation_override")
    high = entity(hass, entry, f"{LIGHT}_normal_override")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": end, "value": 0.0}, blocking=True
    )
    assert c.effective(LIGHT)["end_elevation"] == 0.0  # 0 degrees, not "use global"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": high, "value": 80.0}, blocking=True
    )
    assert c.effective(LIGHT)["normal_pct"] == 80.0
    await hass.services.async_call(
        DOMAIN, "clear_override", {"entity_id": high}, blocking=True
    )
    assert c.effective(LIGHT)["normal_pct"] == c.values["normal_pct"]
    await teardown(hass, entry)


async def test_demo_preview_can_try_a_per_light_window_and_inherit_with_null(
    hass,
) -> None:
    entry, _ = await setup(hass)
    c = entry.runtime_data
    _values, ov = c._clean_preview(
        LIGHT,
        {"overrides": {"start_elevation": 99, "end_elevation": None, "normal": 70}},
    )
    assert ov["start_elevation"] == 40  # clamped to the allowed range
    assert "end_elevation" not in ov  # null = follow the global one
    assert ov["normal"] == 70
    await teardown(hass, entry)
