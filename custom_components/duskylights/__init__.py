"""Dusky Lights: ease lights down with the sun, back up at dawn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform

from .const import DOMAIN
from .controller import Controller
from .services import async_register_services

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS = [Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]

type DuskyConfigEntry = ConfigEntry[Controller]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DuskyConfigEntry) -> bool:
    controller = Controller(hass, entry.options["lights"])
    entry.runtime_data = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    controller.async_start()  # after platforms: restored settings are in place
    entry.async_on_unload(controller.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DuskyConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


__all__ = ["DOMAIN", "async_setup", "async_setup_entry", "async_unload_entry"]
