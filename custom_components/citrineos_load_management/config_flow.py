from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CitrineApiError, CitrineBridgeApiClient
from .const import (
    CONF_BRIDGE_URL,
    CONF_POLL_SECONDS,
    CONF_SHARED_SECRET,
    DEFAULT_POLL_SECONDS,
    DOMAIN,
)


class CitrineConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            bridge_url = user_input[CONF_BRIDGE_URL]
            await self.async_set_unique_id(bridge_url.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = CitrineBridgeApiClient(
                session,
                bridge_url,
                user_input[CONF_SHARED_SECRET],
            )

            try:
                await client.get_health()
                await client.get_stations()
            except CitrineApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=bridge_url,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BRIDGE_URL, default="http://localhost:8095"): str,
                    vol.Required(CONF_SHARED_SECRET): str,
                    vol.Optional(CONF_POLL_SECONDS, default=DEFAULT_POLL_SECONDS): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=300)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CitrineOptionsFlow(config_entry)


class CitrineOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BRIDGE_URL,
                        default=current.get(
                            CONF_BRIDGE_URL,
                            self.config_entry.data[CONF_BRIDGE_URL],
                        ),
                    ): str,
                    vol.Required(
                        CONF_SHARED_SECRET,
                        default=current.get(
                            CONF_SHARED_SECRET,
                            self.config_entry.data[CONF_SHARED_SECRET],
                        ),
                    ): str,
                    vol.Required(
                        CONF_POLL_SECONDS,
                        default=current.get(
                            CONF_POLL_SECONDS,
                            self.config_entry.data.get(CONF_POLL_SECONDS, DEFAULT_POLL_SECONDS),
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
        )
