"""The Dusky sidebar panel: curve graph, settings, lights and demo controls.

The panel is a plain web component (`frontend/dusky-panel.js`, no build step). It
reads and writes the integration's own entities, so it adds no state of its own.
The websocket command below tells it which entity ids to use, so renaming an
entity does not break it.
"""

from __future__ import annotations

import hashlib
import inspect
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from astral import Observer
from astral.sun import elevation as astral_elevation
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CONF_LIGHTS,
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

PANEL_URL = "dusky-lights"
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
    used = set(entry.runtime_data.lights)
    candidates = []
    for st in hass.states.async_all("light"):
        ent = reg.async_get(st.entity_id)
        if st.entity_id in used or (
            ent and (ent.disabled_by or ent.hidden_by or ent.platform == DOMAIN)
        ):
            continue
        candidates.append({"light": st.entity_id, "name": st.name})
    candidates.sort(key=lambda c: c["name"].lower())
    return {
        "build": _installed_commit(hass) or _digest(),
        "settings": settings,
        "lights": lights,
        "candidates": candidates,
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


SUN_STEP_S = 120


def _day_path(hass: HomeAssistant) -> dict[str, Any]:
    """Today's sun elevation every SUN_STEP_S seconds, local midnight to midnight."""
    tz = dt_util.get_default_time_zone()
    today = dt_util.now().date()
    start = datetime.combine(today, time(), tzinfo=tz)
    end = datetime.combine(today + timedelta(days=1), time(), tzinfo=tz)
    observer = Observer(hass.config.latitude, hass.config.longitude)
    t0 = int(start.timestamp())
    t1 = int(end.timestamp())  # a day is 23 or 25 hours long on a clock change
    samples = [
        round(
            astral_elevation(observer, datetime.fromtimestamp(t, UTC)),
            2,
        )
        for t in range(t0, t1, SUN_STEP_S)
    ]
    return {"start": t0 * 1000, "step_s": SUN_STEP_S, "elevations": samples}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/sun_path"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_sun_path(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    connection.send_result(
        msg["id"], await hass.async_add_executor_job(_day_path, hass)
    )


PREVIEW = vol.Schema(
    {
        vol.Optional("settings"): {str: vol.Coerce(float)},
        vol.Optional("overrides"): {str: vol.Coerce(float)},
    }
)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/demo",
        vol.Required("light"): cv.entity_domain("light"),
        vol.Optional("seconds", default=0): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=600)
        ),
        vol.Optional("loop", default=False): cv.boolean,
        vol.Optional("preview"): PREVIEW,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_demo(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Start a demo on one light, optionally with unsaved settings to try."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_loaded", "Dusky Lights is not set up")
        return
    await entries[0].runtime_data.async_start_demo(
        msg["light"],
        seconds=msg["seconds"],
        loop=msg["loop"],
        preview=msg.get("preview"),
    )
    connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/demo_stop"})
@websocket_api.require_admin
@callback
def ws_demo_stop(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        entry.runtime_data.async_stop_demo()
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_lights",
        vol.Required("lights"): vol.All(
            [cv.entity_domain("light")], vol.Length(min=1), vol.Unique()
        ),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set_lights(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Replace the managed lights (what the options form does) and reload."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_loaded", "Dusky Lights is not set up")
        return
    entry = entries[0]
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_LIGHTS: msg["lights"]}
    )
    await hass.config_entries.async_reload(entry.entry_id)
    connection.send_result(msg["id"])


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_set_lights)
    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_demo)
    websocket_api.async_register_command(hass, ws_demo_stop)
    websocket_api.async_register_command(hass, ws_sun_path)


def _installed_commit(hass: HomeAssistant) -> str | None:
    """The commit HACS installed this from, when HACS can tell us (best effort)."""
    try:
        hacs = hass.data.get("hacs")
        repo = hacs.repositories.get_by_full_name("internetofawesome/duskylights")
        return str(repo.data.installed_commit or "")[:7] or None
    except Exception:  # noqa: BLE001 - HACS missing, renamed API, manual install
        return None


def _digest() -> str:
    return hashlib.sha1(
        (Path(__file__).parent / "frontend" / JS).read_bytes()
    ).hexdigest()[:10]


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
        "sidebar_title": "Dusky Lights",
        "sidebar_icon": "mdi:weather-sunset-down",
        # the content hash makes browsers fetch the file again whenever it changes
        "module_url": f"{STATIC_URL}/{JS}?v={version}-{await hass.async_add_executor_job(_digest)}",
        "require_admin": True,
    }
    params = inspect.signature(panel_custom.async_register_panel).parameters
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in params}
    await panel_custom.async_register_panel(hass, **kwargs)


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
