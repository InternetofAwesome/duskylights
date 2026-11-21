"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import Controller


def device_info(
    entry_id: str, light: str | None, light_name: str, hub_id: str | None = None
) -> DeviceInfo:
    """The hub device ("Dusky") or one device per light ("Dusky <light>").

    Entity ids are device name + entity name, so this keeps them short:
    number.dusky_living_room_high, not number.dusky_lights_living_room_...
    """
    if light is None:
        return DeviceInfo(
            identifiers={(DOMAIN, entry_id)}, name="Dusky", manufacturer="Dusky Lights"
        )
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{light}")},
        name=f"Dusky {light_name}",
        manufacturer="Dusky Lights",
        via_device_id=hub_id,
    )


class DuskyEntity(Entity):
    """Entity that refreshes whenever the controller does."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, controller: Controller, entry_id: str, light: str | None = None
    ) -> None:
        self.controller = controller
        self.light = light
        name = light_name(controller.hass, light) if light else ""
        hub = dr.async_get(controller.hass).async_get_device({(DOMAIN, entry_id)})
        self._attr_device_info = device_info(
            entry_id, light, name, hub.id if hub else None
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.add_listener(self.async_write_ha_state))


def light_name(hass, light: str) -> str:
    state = hass.states.get(light)
    return state.name if state else light.split(".", 1)[-1].replace("_", " ").title()
