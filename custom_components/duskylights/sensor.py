"""Read-only sensors: each light's target brightness, and the sun elevation used."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory

from .engine import pct_to_bri
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
        [ElevationSensor(c, entry.entry_id)]
        + [TargetSensor(c, entry.entry_id, light) for light in c.lights]
    )


class TargetSensor(DuskyEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, controller: Controller, entry_id: str, light: str) -> None:
        super().__init__(controller, entry_id)
        self.light = light
        self._attr_unique_id = f"{entry_id}_{light}_target"

    @property
    def name(self) -> str:
        return f"{self.light_name(self.light)} target brightness"

    @property
    def native_value(self) -> float:
        return round(self.controller.target_pct(self.light), 1)

    @property
    def extra_state_attributes(self) -> dict:
        hold = self.controller.holding(self.light)
        return {
            "light": self.light,
            "target_brightness": pct_to_bri(self.controller.target_pct(self.light)),
            "holding": hold is not None,
            "hold_brightness": hold,
            "demo": self.controller.demo_light == self.light,
        }


class ElevationSensor(DuskyEntity, SensorEntity):
    _attr_name = "Sun elevation (interpolated)"
    _attr_native_unit_of_measurement = "°"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller: Controller, entry_id: str) -> None:
        super().__init__(controller, entry_id)
        self._attr_unique_id = f"{entry_id}_elevation"

    @property
    def native_value(self) -> float | None:
        elev = self.controller.live_elevation()
        return None if elev is None else round(elev, 2)
