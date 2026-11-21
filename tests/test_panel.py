"""Backend side of the panel: the websocket command and the registration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.duskylights import panel
from custom_components.duskylights.const import DOMAIN

from .test_integration import LIGHT, setup, teardown


async def test_info_command_maps_entities_for_admins(
    hass: HomeAssistant, hass_ws_client
) -> None:
    entry, _ = await setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/info"})
    msg = await client.receive_json()
    assert msg["success"], msg
    info = msg["result"]
    assert info["settings"]["normal_pct"] == "number.dusky_high"
    assert info["settings"]["start_elevation"] == "number.dusky_start_elevation"
    (light,) = info["lights"]
    assert light["light"] == LIGHT
    assert light["high"] == "number.dusky_test_lamp_high"
    assert light["release"] == "button.dusky_test_lamp_release"
    assert light["target"] == "sensor.dusky_test_lamp_target"
    assert info["demo"]["switch"] == "switch.dusky_demo"
    assert info["release_all"] == "button.dusky_release_all"
    assert info["elevation"] == "sensor.dusky_sun_elevation"
    await teardown(hass, entry)


async def test_info_command_is_admin_only(
    hass: HomeAssistant, hass_ws_client, hass_read_only_access_token
) -> None:
    entry, _ = await setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/info"})
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "unauthorized"
    await teardown(hass, entry)


async def test_panel_is_registered_admin_only_and_served(hass: HomeAssistant) -> None:
    await async_setup_component(hass, "http", {})
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch.object(panel.panel_custom, "async_register_panel", AsyncMock()) as reg:
        await panel.async_register_panel(hass, "9.9.9")
    kwargs = reg.await_args.kwargs
    assert kwargs["frontend_url_path"] == "dusky"
    assert kwargs["webcomponent_name"] == "dusky-panel"
    assert kwargs["require_admin"] is True
    assert kwargs["module_url"] == "/duskylights_static/dusky-panel.js?v=9.9.9"
    (static,) = hass.http.async_register_static_paths.await_args.args[0]
    assert static.url_path == "/duskylights_static"
    assert (panel.Path(static.path) / "dusky-panel.js").is_file()


async def test_registration_skips_arguments_this_home_assistant_lacks(
    hass: HomeAssistant,
) -> None:
    hass.http = MagicMock(async_register_static_paths=AsyncMock())

    async def old_signature(
        hass,
        frontend_url_path,
        webcomponent_name,
        module_url=None,
        sidebar_title=None,
        sidebar_icon=None,
        require_admin=False,
    ):
        old_signature.seen = (frontend_url_path, require_admin)

    with patch.object(panel.panel_custom, "async_register_panel", old_signature):
        await panel.async_register_panel(hass, "1")  # must not pass config_panel_domain
    assert old_signature.seen == ("dusky", True)


async def test_demo_command_previews_unsaved_settings_only_for_the_demo(
    hass: HomeAssistant, hass_ws_client
) -> None:
    entry, _ = await setup(hass)
    c = entry.runtime_data
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/demo",
            "light": LIGHT,
            "preview": {"settings": {"normal_pct": 80}, "overrides": {"floor": 30}},
        }
    )
    assert (await client.receive_json())["success"]
    assert c._demo_values["normal_pct"] == 80  # previewed...
    assert c._demo_ov["floor"] == 30
    assert c.values["normal_pct"] == 50  # ...but nothing saved
    assert c.overrides[LIGHT]["floor"] == 0
    await client.send_json({"id": 2, "type": f"{DOMAIN}/demo_stop"})
    assert (await client.receive_json())["success"]
    assert c._demo_values is None
    await teardown(hass, entry)
