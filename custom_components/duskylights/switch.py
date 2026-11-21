"""The demo switch: on while a demo runs; turning it on starts one."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity

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
    async_add_entities([DemoSwitch(entry.runtime_data, entry.entry_id)])


class DemoSwitch(DuskyEntity, SwitchEntity):
    _attr_name = "Demo"

    def __init__(self, controller: Controller, entry_id: str) -> None:
        super().__init__(controller, entry_id)
        self._attr_unique_id = f"{entry_id}_demo"

    @property
    def is_on(self) -> bool:
        return self.controller.demo is not None

    @property
    def available(self) -> bool:
        return self.controller.demo_choice is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.controller.async_start_demo(
            self.controller.demo_choice,
            seconds=self.controller.demo_seconds,
            loop=self.controller.demo_loop,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.async_stop_demo()
