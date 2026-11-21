"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import Controller


def device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="Dusky Lights",
        manufacturer="Dusky Lights",
    )


class DuskyEntity(Entity):
    """Entity that refreshes whenever the controller does."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: Controller, entry_id: str) -> None:
        self.controller = controller
        self._attr_device_info = device_info(entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.add_listener(self.async_write_ha_state))

    def light_name(self, light: str) -> str:
        state = self.hass.states.get(light) if self.hass else None
        return (
            state.name if state else light.split(".", 1)[-1].replace("_", " ").title()
        )
