"""Demo choices: which light, and whether to play once or loop."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity

from .entity import DuskyEntity, light_name

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import DuskyConfigEntry
    from .controller import Controller

ONCE, LOOP = "Once", "Loop"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DuskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities(
        [DemoLightSelect(c, entry.entry_id), DemoRepeatSelect(c, entry.entry_id)]
    )


class DemoLightSelect(DuskyEntity, SelectEntity):
    _attr_name = "Demo light"

    def __init__(self, controller: Controller, entry_id: str) -> None:
        super().__init__(controller, entry_id)
        self._attr_unique_id = f"{entry_id}_demo_light"

    def _labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for light in self.controller.lights:
            name = light_name(self.controller.hass, light)
            labels[f"{name} ({light})" if name in labels.values() else name] = light
        return labels

    @property
    def options(self) -> list[str]:
        return list(self._labels())

    @property
    def current_option(self) -> str | None:
        for label, light in self._labels().items():
            if light == self.controller.demo_choice:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        self.controller.demo_choice = self._labels()[option]
        self.async_write_ha_state()


class DemoRepeatSelect(DuskyEntity, SelectEntity):
    _attr_name = "Demo repeat"

    def __init__(self, controller: Controller, entry_id: str) -> None:
        super().__init__(controller, entry_id)
        self._attr_options = [ONCE, LOOP]
        self._attr_unique_id = f"{entry_id}_demo_repeat"

    @property
    def current_option(self) -> str:
        return LOOP if self.controller.demo_loop else ONCE

    async def async_select_option(self, option: str) -> None:
        self.controller.demo_loop = option == LOOP
        self.async_write_ha_state()
