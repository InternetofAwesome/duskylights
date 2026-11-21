"""Buttons that release manual holds."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity

from .entity import DuskyEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import DuskyConfigEntry
    from .controller import Controller


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities(
        [ReleaseButton(c, entry.entry_id, None)]
        + [ReleaseButton(c, entry.entry_id, light) for light in c.lights]
    )


class ReleaseButton(DuskyEntity, ButtonEntity):
    def __init__(
        self, controller: Controller, entry_id: str, light: str | None
    ) -> None:
        super().__init__(controller, entry_id, light)
        self._attr_name = "Release all" if light is None else "Release"
        self._attr_unique_id = f"{entry_id}_release_{light or 'all'}"

    async def async_press(self) -> None:
        self.controller.async_release(None if self.light is None else [self.light])
