"""Domain services: release, demo, demo_stop."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SERVICE_DEMO, SERVICE_DEMO_STOP, SERVICE_RELEASE

if TYPE_CHECKING:
    from .controller import Controller

RELEASE_SCHEMA = vol.Schema({vol.Optional("entity_id"): cv.entity_ids})
DEMO_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_domain("light"),
        vol.Optional("duration", default=10): vol.All(
            vol.Coerce(float), vol.Range(min=0.05, max=1440)
        ),
        vol.Optional("date"): cv.date,
        vol.Optional("start_hour", default=12): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=24)
        ),
        vol.Optional("loop", default=False): cv.boolean,
    }
)


def _controller(hass: HomeAssistant) -> Controller:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Dusky Lights is not set up")
    return entries[0].runtime_data


def async_register_services(hass: HomeAssistant) -> None:
    async def release(call: ServiceCall) -> None:
        _controller(hass).async_release(call.data.get("entity_id"))

    async def demo(call: ServiceCall) -> None:
        await _controller(hass).async_start_demo(
            call.data["entity_id"],
            duration_min=call.data["duration"],
            day=call.data.get("date"),
            start_hour=call.data["start_hour"],
            loop=call.data["loop"],
        )

    async def demo_stop(call: ServiceCall) -> None:
        _controller(hass).async_stop_demo()

    hass.services.async_register(DOMAIN, SERVICE_RELEASE, release, RELEASE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DEMO, demo, DEMO_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DEMO_STOP, demo_stop)
