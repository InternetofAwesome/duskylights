"""Config flow: pick the lights to manage (changeable later in options)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_LIGHTS, DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LIGHTS): vol.All(
            EntitySelector(EntitySelectorConfig(domain="light", multiple=True)),
            vol.Length(min=1),
        )
    }
)


class DuskyConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Dusky Lights",
                data={},
                options={CONF_LIGHTS: user_input[CONF_LIGHTS]},
            )
        return self.async_show_form(step_id="user", data_schema=SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DuskyOptionsFlow:
        return DuskyOptionsFlow()


class DuskyOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={CONF_LIGHTS: user_input[CONF_LIGHTS]})
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA, {CONF_LIGHTS: self.config_entry.options.get(CONF_LIGHTS, [])}
            ),
        )
