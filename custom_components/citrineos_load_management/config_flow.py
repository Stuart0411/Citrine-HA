from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CitrineApiError, CitrineBridgeApiClient, CitrineDirectApiClient
from .const import (
    CONF_BRIDGE_URL,
    CONF_CITRINEOS_BASE_URL,
    CONF_CITRINEOS_OCPP16_PREFIX,
    CONF_CITRINEOS_OCPP2_PREFIX,
    CONF_CITRINEOS_STATIONS_URL,
    CONF_MODE,
    CONF_POLL_SECONDS,
    CONF_SHARED_SECRET,
    CONF_STATION_DEFAULT_MAX_WATTS,
    CONF_STATION_DEFAULT_PROTOCOL,
    CONF_STATION_DEFAULT_TENANT_ID,
    CONF_STATION_DEFAULT_WEIGHT,
    DEFAULT_CITRINEOS_OCPP16_PREFIX,
    DEFAULT_CITRINEOS_OCPP2_PREFIX,
    DEFAULT_POLL_SECONDS,
    DEFAULT_STATION_DEFAULT_MAX_WATTS,
    DEFAULT_STATION_DEFAULT_PROTOCOL,
    DEFAULT_STATION_DEFAULT_TENANT_ID,
    DEFAULT_STATION_DEFAULT_WEIGHT,
    DOMAIN,
    MODE_BRIDGE,
    MODE_DIRECT,
)


class CitrineConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            mode = user_input[CONF_MODE]
            if mode == MODE_DIRECT:
                return await self.async_step_direct()
            return await self.async_step_bridge()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODE, default=MODE_DIRECT): vol.In([MODE_DIRECT, MODE_BRIDGE]),
                }
            ),
        )

    async def async_step_bridge(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            bridge_url = user_input[CONF_BRIDGE_URL]
            user_input[CONF_MODE] = MODE_BRIDGE
            await self.async_set_unique_id(f"{MODE_BRIDGE}:{bridge_url.lower()}")
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
            step_id="bridge",
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

    async def async_step_direct(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_CITRINEOS_BASE_URL]
            user_input[CONF_MODE] = MODE_DIRECT
            await self.async_set_unique_id(f"{MODE_DIRECT}:{base_url.lower()}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = CitrineDirectApiClient(
                session,
                base_url,
                stations_url=user_input.get(CONF_CITRINEOS_STATIONS_URL),
                ocpp2_prefix=user_input[CONF_CITRINEOS_OCPP2_PREFIX],
                ocpp16_prefix=user_input[CONF_CITRINEOS_OCPP16_PREFIX],
                station_default_tenant_id=user_input[CONF_STATION_DEFAULT_TENANT_ID],
                station_default_protocol=user_input[CONF_STATION_DEFAULT_PROTOCOL],
                station_default_max_watts=user_input[CONF_STATION_DEFAULT_MAX_WATTS],
                station_default_weight=user_input[CONF_STATION_DEFAULT_WEIGHT],
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
                    title=f"CitrineOS Direct ({base_url})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="direct",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CITRINEOS_BASE_URL, default="http://localhost:8080"): str,
                    vol.Optional(CONF_CITRINEOS_STATIONS_URL): str,
                    vol.Required(
                        CONF_CITRINEOS_OCPP2_PREFIX,
                        default=DEFAULT_CITRINEOS_OCPP2_PREFIX,
                    ): str,
                    vol.Required(
                        CONF_CITRINEOS_OCPP16_PREFIX,
                        default=DEFAULT_CITRINEOS_OCPP16_PREFIX,
                    ): str,
                    vol.Required(
                        CONF_STATION_DEFAULT_TENANT_ID,
                        default=DEFAULT_STATION_DEFAULT_TENANT_ID,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Required(
                        CONF_STATION_DEFAULT_PROTOCOL,
                        default=DEFAULT_STATION_DEFAULT_PROTOCOL,
                    ): vol.In(["2.0.1", "1.6"]),
                    vol.Required(
                        CONF_STATION_DEFAULT_MAX_WATTS,
                        default=DEFAULT_STATION_DEFAULT_MAX_WATTS,
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    vol.Required(
                        CONF_STATION_DEFAULT_WEIGHT,
                        default=DEFAULT_STATION_DEFAULT_WEIGHT,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
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
        mode = current.get(CONF_MODE, self.config_entry.data.get(CONF_MODE, MODE_BRIDGE))

        if mode == MODE_DIRECT:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CITRINEOS_BASE_URL,
                            default=current.get(
                                CONF_CITRINEOS_BASE_URL,
                                self.config_entry.data.get(CONF_CITRINEOS_BASE_URL, "http://localhost:8080"),
                            ),
                        ): str,
                        vol.Optional(
                            CONF_CITRINEOS_STATIONS_URL,
                            default=current.get(
                                CONF_CITRINEOS_STATIONS_URL,
                                self.config_entry.data.get(CONF_CITRINEOS_STATIONS_URL, ""),
                            ),
                        ): str,
                        vol.Required(
                            CONF_CITRINEOS_OCPP2_PREFIX,
                            default=current.get(
                                CONF_CITRINEOS_OCPP2_PREFIX,
                                self.config_entry.data.get(
                                    CONF_CITRINEOS_OCPP2_PREFIX,
                                    DEFAULT_CITRINEOS_OCPP2_PREFIX,
                                ),
                            ),
                        ): str,
                        vol.Required(
                            CONF_CITRINEOS_OCPP16_PREFIX,
                            default=current.get(
                                CONF_CITRINEOS_OCPP16_PREFIX,
                                self.config_entry.data.get(
                                    CONF_CITRINEOS_OCPP16_PREFIX,
                                    DEFAULT_CITRINEOS_OCPP16_PREFIX,
                                ),
                            ),
                        ): str,
                        vol.Required(
                            CONF_STATION_DEFAULT_TENANT_ID,
                            default=current.get(
                                CONF_STATION_DEFAULT_TENANT_ID,
                                self.config_entry.data.get(
                                    CONF_STATION_DEFAULT_TENANT_ID,
                                    DEFAULT_STATION_DEFAULT_TENANT_ID,
                                ),
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                        vol.Required(
                            CONF_STATION_DEFAULT_PROTOCOL,
                            default=current.get(
                                CONF_STATION_DEFAULT_PROTOCOL,
                                self.config_entry.data.get(
                                    CONF_STATION_DEFAULT_PROTOCOL,
                                    DEFAULT_STATION_DEFAULT_PROTOCOL,
                                ),
                            ),
                        ): vol.In(["2.0.1", "1.6"]),
                        vol.Required(
                            CONF_STATION_DEFAULT_MAX_WATTS,
                            default=current.get(
                                CONF_STATION_DEFAULT_MAX_WATTS,
                                self.config_entry.data.get(
                                    CONF_STATION_DEFAULT_MAX_WATTS,
                                    DEFAULT_STATION_DEFAULT_MAX_WATTS,
                                ),
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                        vol.Required(
                            CONF_STATION_DEFAULT_WEIGHT,
                            default=current.get(
                                CONF_STATION_DEFAULT_WEIGHT,
                                self.config_entry.data.get(
                                    CONF_STATION_DEFAULT_WEIGHT,
                                    DEFAULT_STATION_DEFAULT_WEIGHT,
                                ),
                            ),
                        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
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
