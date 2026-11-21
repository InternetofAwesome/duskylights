"""Settings as number entities (global defaults and per-light overrides)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory

from .const import DEFAULTS, GLOBAL_NUMBERS
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
    entities: list[DuskyNumber] = [
        GlobalNumber(c, entry.entry_id, *spec) for spec in GLOBAL_NUMBERS
    ]
    for light in c.lights:
        for kind, label in (("normal", "High"), ("floor", "Low")):
            entities.append(OverrideNumber(c, entry.entry_id, light, kind, label))
    entities.append(DemoLengthNumber(c, entry.entry_id))
    async_add_entities(entities)


class DuskyNumber(DuskyEntity, RestoreNumber):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    default: float = 0.0

    def _apply(self, value: float, *, tick: bool) -> None:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        value = (
            last.native_value
            if last and last.native_value is not None
            else self.default
        )
        self._attr_native_value = value
        self._apply(
            value, tick=False
        )  # restored silently; the controller isn't running yet

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._apply(value, tick=True)
        self.async_write_ha_state()


class GlobalNumber(DuskyNumber):
    def __init__(
        self,
        controller: Controller,
        entry_id: str,
        key: str,
        name: str,
        lo: float,
        hi: float,
        step: float,
        unit: str | None,
    ) -> None:
        super().__init__(controller, entry_id)
        self.key = key
        self.default = DEFAULTS[key]
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_native_value = self.default

    def _apply(self, value: float, *, tick: bool) -> None:
        self.controller.set_value(self.key, value, tick=tick)


class OverrideNumber(DuskyNumber):
    """Per-light override; 0 means "use the global value"."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    default = 0.0

    def __init__(
        self, controller: Controller, entry_id: str, light: str, kind: str, label: str
    ) -> None:
        super().__init__(controller, entry_id, light)
        self.kind = kind
        self._attr_name = label
        self._attr_unique_id = f"{entry_id}_{light}_{kind}_override"
        self._attr_native_value = 0.0

    def _apply(self, value: float, *, tick: bool) -> None:
        self.controller.set_override(self.light, self.kind, value, tick=tick)


class DemoLengthNumber(DuskyNumber):
    """Length of one demo cycle in seconds; 0 = shortest with steps <= 1 %."""

    _attr_name = "Demo length"
    _attr_native_min_value = 0
    _attr_native_max_value = 600
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "s"
    _attr_entity_category = None

    def __init__(self, controller: Controller, entry_id: str) -> None:
        super().__init__(controller, entry_id)
        self._attr_unique_id = f"{entry_id}_demo_length"
        self._attr_native_value = 0.0

    def _apply(self, value: float, *, tick: bool) -> None:
        self.controller.demo_seconds = float(value)
