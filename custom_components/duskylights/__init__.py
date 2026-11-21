"""Dusky Lights: ease lights down with the sun, back up at dawn."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .controller import Controller
from .panel import (
    async_register_panel,
    async_remove_panel,
    async_setup_websocket,
)
from .services import async_register_services

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

MANIFEST_VERSION = json.loads(
    (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
)["version"]

PLATFORMS = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type DuskyConfigEntry = ConfigEntry[Controller]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_register_services(hass)
    async_setup_websocket(hass)
    return True


_LIGHT_ID = re.compile(r"light\.[a-z0-9_]+")


@callback
def _prune_removed_lights(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop entities and devices of lights that were removed from the options."""
    keep = set(entry.options["lights"])
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        found = _LIGHT_ID.findall(ent.unique_id.removeprefix(entry.entry_id))
        if found and not set(found) <= keep:
            ent_reg.async_remove(ent.entity_id)
    dev_reg = dr.async_get(hass)
    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        for domain, ident in dev.identifiers:
            light = ident.removeprefix(f"{entry.entry_id}_")
            if domain == DOMAIN and light != ident and light not in keep:
                dev_reg.async_remove_device(dev.id)


async def async_setup_entry(hass: HomeAssistant, entry: DuskyConfigEntry) -> bool:
    _prune_removed_lights(hass, entry)
    controller = Controller(hass, entry.options["lights"])
    entry.runtime_data = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    controller.async_start()  # after platforms: restored settings are in place
    await async_register_panel(hass, MANIFEST_VERSION)
    entry.async_on_unload(lambda: async_remove_panel(hass))
    entry.async_on_unload(controller.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DuskyConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


__all__ = ["DOMAIN", "async_setup", "async_setup_entry", "async_unload_entry"]
