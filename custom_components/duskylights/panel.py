"""The Dusky sidebar panel: curve graph, settings, lights and demo controls.

The panel is a plain web component (`frontend/dusky-panel.js`, no build step). It
reads and writes the integration's own entities, so it adds no state of its own.
The websocket command below tells it which entity ids to use, so renaming an
entity does not break it.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    K_END,
    K_FLOOR,
    K_NORMAL,
    K_SHARP_END,
    K_SHARP_START,
    K_START,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

PANEL_URL = "dusky"
STATIC_URL = f"/{DOMAIN}_static"
JS = "dusky-panel.js"
_STATIC_DONE = f"{DOMAIN}_static_done"


def _entity(reg: er.EntityRegistry, domain: str, unique_id: str) -> str | None:
    return reg.async_get_entity_id(domain, DOMAIN, unique_id)


def build_info(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Entity ids the panel needs, looked up by unique id (survives renames)."""
    reg = er.async_get(hass)
    eid = entry.entry_id
    settings = {
        key: _entity(reg, "number", f"{eid}_{key}")
        for key in (K_START, K_END, K_NORMAL, K_FLOOR, K_SHARP_START, K_SHARP_END)
    }
    lights = []
    for light in entry.runtime_data.lights:
        state = hass.states.get(light)
        lights.append(
            {
                "light": light,
                "name": state.name if state else light,
                "high": _entity(reg, "number", f"{eid}_{light}_normal_override"),
                "low": _entity(reg, "number", f"{eid}_{light}_floor_override"),
                "release": _entity(reg, "button", f"{eid}_release_{light}"),
                "target": _entity(reg, "sensor", f"{eid}_{light}_target"),
            }
        )
    return {
        "settings": settings,
        "lights": lights,
        "release_all": _entity(reg, "button", f"{eid}_release_all"),
        "elevation": _entity(reg, "sensor", f"{eid}_elevation"),
        "demo": {
            "switch": _entity(reg, "switch", f"{eid}_demo"),
            "light": _entity(reg, "select", f"{eid}_demo_light"),
            "repeat": _entity(reg, "select", f"{eid}_demo_repeat"),
            "length": _entity(reg, "number", f"{eid}_demo_length"),
        },
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info"})
@websocket_api.require_admin
@callback
def ws_info(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_loaded", "Dusky Lights is not set up")
        return
    connection.send_result(msg["id"], build_info(hass, entries[0]))


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_info)


async def async_register_panel(hass: HomeAssistant, version: str) -> None:
    """Serve the panel's JavaScript and add the admin-only sidebar entry."""
    if not hass.data.get(_STATIC_DONE):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL, str(Path(__file__).parent / "frontend"), False
                )
            ]
        )
        hass.data[_STATIC_DONE] = True
    kwargs: dict[str, Any] = {
        "frontend_url_path": PANEL_URL,
        "webcomponent_name": "dusky-panel",
        "sidebar_title": "Dusky",
        "sidebar_icon": "mdi:weather-sunset-down",
        "module_url": f"{STATIC_URL}/{JS}?v={version}",
        "require_admin": True,
        # Makes this the integration's configure page, where HA supports it.
        "config_panel_domain": DOMAIN,
    }
    params = inspect.signature(panel_custom.async_register_panel).parameters
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in params}
    await panel_custom.async_register_panel(hass, **kwargs)


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
