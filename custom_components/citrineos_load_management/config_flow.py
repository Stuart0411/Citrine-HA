from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CitrineApiError, CitrineBridgeApiClient, CitrineDirectApiClient
from .const import (
    CONF_BRIDGE_URL,
    CONF_CHARGERS,
    CONF_CITRINEOS_BASE_URL,
    CONF_CITRINEOS_OCPP16_PREFIX,
    CONF_CITRINEOS_OCPP2_PREFIX,
    CONF_CITRINEOS_STATIONS_URL,
    CONF_GROUPS,
    CONF_MANUAL_STATIONS_JSON,
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

_LOGGER = logging.getLogger(__name__)


class CitrineConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._last_error_detail = "None"

    def _set_last_error_detail(self, detail: str) -> None:
        cleaned = detail.strip() if isinstance(detail, str) else ""
        self._last_error_detail = cleaned[:300] if cleaned else "None"

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
            self._set_last_error_detail("None")

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
            except CitrineApiError as err:
                _LOGGER.warning("Bridge mode validation failed for %s: %s", bridge_url, err)
                self._set_last_error_detail(str(err))
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error while validating bridge mode for %s", bridge_url)
                self._set_last_error_detail(str(err))
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
            description_placeholders={"last_error": self._last_error_detail},
        )

    async def async_step_direct(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._set_last_error_detail("None")

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
                manual_stations_json=user_input.get(CONF_MANUAL_STATIONS_JSON),
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
            except CitrineApiError as err:
                _LOGGER.warning("Direct mode validation failed for %s: %s", base_url, err)
                self._set_last_error_detail(str(err))
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error while validating direct mode for %s", base_url)
                self._set_last_error_detail(str(err))
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
                    vol.Optional(CONF_MANUAL_STATIONS_JSON): str,
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
            description_placeholders={"last_error": self._last_error_detail},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CitrineOptionsFlow(config_entry)


class CitrineOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._options: dict[str, Any] = {
            **dict(config_entry.data),
            **dict(config_entry.options),
        }
        self._options.setdefault(CONF_CHARGERS, [])
        self._options.setdefault(CONF_GROUPS, [])
        self._editing_station_id: str | None = None
        self._editing_group_id: str | None = None

    async def async_step_init(self, _user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "connection_settings",
                "add_charger",
                "edit_charger_select",
                "delete_charger",
                "add_group",
                "edit_group_select",
                "delete_group",
                "save",
            ],
        )

    async def async_step_save(self, _user_input: dict[str, Any] | None = None):
        self._options[CONF_MODE] = self._mode
        return self.async_create_entry(title="", data=self._options)

    async def async_step_connection_settings(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            for key, value in user_input.items():
                self._options[key] = value
            return await self.async_step_init()

        if self._mode == MODE_DIRECT:
            return self.async_show_form(
                step_id="connection_settings",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_CITRINEOS_BASE_URL,
                            default=self._options.get(CONF_CITRINEOS_BASE_URL, "http://localhost:8080"),
                        ): str,
                        vol.Optional(
                            CONF_CITRINEOS_STATIONS_URL,
                            default=self._options.get(CONF_CITRINEOS_STATIONS_URL, ""),
                        ): str,
                        vol.Optional(
                            CONF_MANUAL_STATIONS_JSON,
                            default=self._options.get(CONF_MANUAL_STATIONS_JSON, ""),
                        ): str,
                        vol.Required(
                            CONF_CITRINEOS_OCPP2_PREFIX,
                            default=self._options.get(CONF_CITRINEOS_OCPP2_PREFIX, DEFAULT_CITRINEOS_OCPP2_PREFIX),
                        ): str,
                        vol.Required(
                            CONF_CITRINEOS_OCPP16_PREFIX,
                            default=self._options.get(CONF_CITRINEOS_OCPP16_PREFIX, DEFAULT_CITRINEOS_OCPP16_PREFIX),
                        ): str,
                        vol.Required(
                            CONF_STATION_DEFAULT_TENANT_ID,
                            default=self._options.get(CONF_STATION_DEFAULT_TENANT_ID, DEFAULT_STATION_DEFAULT_TENANT_ID),
                        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                        vol.Required(
                            CONF_STATION_DEFAULT_PROTOCOL,
                            default=self._options.get(CONF_STATION_DEFAULT_PROTOCOL, DEFAULT_STATION_DEFAULT_PROTOCOL),
                        ): vol.In(["2.0.1", "1.6"]),
                        vol.Required(
                            CONF_STATION_DEFAULT_MAX_WATTS,
                            default=self._options.get(CONF_STATION_DEFAULT_MAX_WATTS, DEFAULT_STATION_DEFAULT_MAX_WATTS),
                        ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                        vol.Required(
                            CONF_STATION_DEFAULT_WEIGHT,
                            default=self._options.get(CONF_STATION_DEFAULT_WEIGHT, DEFAULT_STATION_DEFAULT_WEIGHT),
                        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                        vol.Required(
                            CONF_POLL_SECONDS,
                            default=self._options.get(CONF_POLL_SECONDS, DEFAULT_POLL_SECONDS),
                        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                    }
                ),
            )

        return self.async_show_form(
            step_id="connection_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BRIDGE_URL,
                        default=self._options.get(CONF_BRIDGE_URL, "http://localhost:8095"),
                    ): str,
                    vol.Required(
                        CONF_SHARED_SECRET,
                        default=self._options.get(CONF_SHARED_SECRET, ""),
                    ): str,
                    vol.Required(
                        CONF_POLL_SECONDS,
                        default=self._options.get(CONF_POLL_SECONDS, DEFAULT_POLL_SECONDS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
        )

    async def async_step_add_charger(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            station_id = user_input["station_id"].strip()
            if station_id in {charger["stationId"] for charger in self._chargers}:
                errors["base"] = "duplicate_station_id"
            else:
                self._chargers.append(self._charger_from_input(user_input))
                return await self.async_step_init()

        return self.async_show_form(
            step_id="add_charger",
            data_schema=self._charger_schema(),
            errors=errors,
        )

    async def async_step_edit_charger_select(self, user_input: dict[str, Any] | None = None):
        chargers = self._chargers
        if len(chargers) == 0:
            return self.async_abort(reason="no_chargers")

        if user_input is not None:
            self._editing_station_id = user_input["station_id"]
            return await self.async_step_edit_charger()

        choices = {charger["stationId"]: charger["stationId"] for charger in chargers}
        return self.async_show_form(
            step_id="edit_charger_select",
            data_schema=vol.Schema(
                {
                    vol.Required("station_id"): vol.In(choices),
                }
            ),
        )

    async def async_step_edit_charger(self, user_input: dict[str, Any] | None = None):
        current = self._charger_by_station_id(self._editing_station_id)
        if current is None:
            return self.async_abort(reason="charger_not_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            next_station_id = user_input["station_id"].strip()
            existing_station_ids = {
                charger["stationId"]
                for charger in self._chargers
                if charger["stationId"] != current["stationId"]
            }
            if next_station_id in existing_station_ids:
                errors["base"] = "duplicate_station_id"
            else:
                updated = self._charger_from_input(user_input)
                self._replace_charger(current["stationId"], updated)
                self._rename_station_references(current["stationId"], updated["stationId"])
                return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_charger",
            data_schema=self._charger_schema(current),
            errors=errors,
        )

    async def async_step_delete_charger(self, user_input: dict[str, Any] | None = None):
        chargers = self._chargers
        if len(chargers) == 0:
            return self.async_abort(reason="no_chargers")

        if user_input is not None:
            station_id = user_input["station_id"]
            self._options[CONF_CHARGERS] = [
                charger for charger in chargers if charger["stationId"] != station_id
            ]
            self._remove_station_from_groups(station_id)
            return await self.async_step_init()

        choices = {charger["stationId"]: charger["stationId"] for charger in chargers}
        return self.async_show_form(
            step_id="delete_charger",
            data_schema=vol.Schema(
                {
                    vol.Required("station_id"): vol.In(choices),
                }
            ),
        )

    async def async_step_add_group(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            group_id = user_input["group_id"].strip()
            if group_id in {group["groupId"] for group in self._groups}:
                errors["base"] = "duplicate_group_id"
            else:
                station_ids = self._parse_csv_list(user_input.get("station_ids", ""))
                if not self._station_ids_exist(station_ids):
                    errors["base"] = "unknown_station_id"
                else:
                    self._groups.append(
                        {
                            "groupId": group_id,
                            "stationIds": station_ids,
                            "maxWatts": user_input.get("max_watts"),
                        }
                    )
                    return await self.async_step_init()

        return self.async_show_form(
            step_id="add_group",
            data_schema=self._group_schema(),
            errors=errors,
        )

    async def async_step_edit_group_select(self, user_input: dict[str, Any] | None = None):
        groups = self._groups
        if len(groups) == 0:
            return self.async_abort(reason="no_groups")

        if user_input is not None:
            self._editing_group_id = user_input["group_id"]
            return await self.async_step_edit_group()

        choices = {group["groupId"]: group["groupId"] for group in groups}
        return self.async_show_form(
            step_id="edit_group_select",
            data_schema=vol.Schema(
                {
                    vol.Required("group_id"): vol.In(choices),
                }
            ),
        )

    async def async_step_edit_group(self, user_input: dict[str, Any] | None = None):
        current = self._group_by_id(self._editing_group_id)
        if current is None:
            return self.async_abort(reason="group_not_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            next_group_id = user_input["group_id"].strip()
            existing_group_ids = {
                group["groupId"]
                for group in self._groups
                if group["groupId"] != current["groupId"]
            }
            if next_group_id in existing_group_ids:
                errors["base"] = "duplicate_group_id"
            else:
                station_ids = self._parse_csv_list(user_input.get("station_ids", ""))
                if not self._station_ids_exist(station_ids):
                    errors["base"] = "unknown_station_id"
                else:
                    updated = {
                        "groupId": next_group_id,
                        "stationIds": station_ids,
                        "maxWatts": user_input.get("max_watts"),
                    }
                    self._replace_group(current["groupId"], updated)
                    return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_group",
            data_schema=self._group_schema(current),
            errors=errors,
        )

    async def async_step_delete_group(self, user_input: dict[str, Any] | None = None):
        groups = self._groups
        if len(groups) == 0:
            return self.async_abort(reason="no_groups")

        if user_input is not None:
            group_id = user_input["group_id"]
            self._options[CONF_GROUPS] = [
                group for group in groups if group["groupId"] != group_id
            ]
            return await self.async_step_init()

        choices = {group["groupId"]: group["groupId"] for group in groups}
        return self.async_show_form(
            step_id="delete_group",
            data_schema=vol.Schema(
                {
                    vol.Required("group_id"): vol.In(choices),
                }
            ),
        )

    @property
    def _mode(self) -> str:
        return str(self._options.get(CONF_MODE, MODE_BRIDGE))

    @property
    def _chargers(self) -> list[dict[str, Any]]:
        chargers = self._options.get(CONF_CHARGERS)
        if not isinstance(chargers, list):
            chargers = []
            self._options[CONF_CHARGERS] = chargers
        return chargers

    @property
    def _groups(self) -> list[dict[str, Any]]:
        groups = self._options.get(CONF_GROUPS)
        if not isinstance(groups, list):
            groups = []
            self._options[CONF_GROUPS] = groups
        return groups

    def _charger_schema(self, existing: dict[str, Any] | None = None) -> vol.Schema:
        current = existing or {}
        return vol.Schema(
            {
                vol.Required("station_id", default=current.get("stationId", "")): str,
                vol.Required("protocol", default=current.get("protocol", "1.6")): vol.In(["2.0.1", "1.6"]),
                vol.Required("tenant_id", default=current.get("tenantId", 1)): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required("max_watts", default=current.get("maxWatts", DEFAULT_STATION_DEFAULT_MAX_WATTS)): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Required("weight", default=current.get("weight", DEFAULT_STATION_DEFAULT_WEIGHT)): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
                vol.Optional("evse_id", default=current.get("evseId") or ""): vol.Any(
                    "", vol.All(vol.Coerce(int), vol.Range(min=0))
                ),
                vol.Optional("connector_id", default=current.get("connectorId") or ""): vol.Any(
                    "", vol.All(vol.Coerce(int), vol.Range(min=0))
                ),
                vol.Optional("group_ids", default=", ".join(current.get("groupIds", []))): str,
            }
        )

    def _group_schema(self, existing: dict[str, Any] | None = None) -> vol.Schema:
        current = existing or {}
        station_ids = current.get("stationIds", [])
        return vol.Schema(
            {
                vol.Required("group_id", default=current.get("groupId", "")): str,
                vol.Optional("station_ids", default=", ".join(station_ids)): str,
                vol.Optional("max_watts", default=current.get("maxWatts") or ""): vol.Any(
                    "", vol.All(vol.Coerce(int), vol.Range(min=0))
                ),
            }
        )

    def _charger_from_input(self, user_input: dict[str, Any]) -> dict[str, Any]:
        station_id = user_input["station_id"].strip()
        evse_id = user_input.get("evse_id")
        connector_id = user_input.get("connector_id")
        group_ids = self._parse_csv_list(user_input.get("group_ids", ""))

        return {
            "stationId": station_id,
            "protocol": user_input["protocol"],
            "tenantId": int(user_input["tenant_id"]),
            "maxWatts": int(user_input["max_watts"]),
            "weight": int(user_input["weight"]),
            "evseId": int(evse_id) if evse_id != "" else None,
            "connectorId": int(connector_id) if connector_id != "" else None,
            "groupIds": group_ids,
        }

    def _charger_by_station_id(self, station_id: str | None) -> dict[str, Any] | None:
        if station_id is None:
            return None
        for charger in self._chargers:
            if charger.get("stationId") == station_id:
                return charger
        return None

    def _group_by_id(self, group_id: str | None) -> dict[str, Any] | None:
        if group_id is None:
            return None
        for group in self._groups:
            if group.get("groupId") == group_id:
                return group
        return None

    def _replace_charger(self, old_station_id: str, updated: dict[str, Any]) -> None:
        self._options[CONF_CHARGERS] = [
            updated if charger.get("stationId") == old_station_id else charger
            for charger in self._chargers
        ]

    def _replace_group(self, old_group_id: str, updated: dict[str, Any]) -> None:
        self._options[CONF_GROUPS] = [
            updated if group.get("groupId") == old_group_id else group
            for group in self._groups
        ]

    def _rename_station_references(self, old_station_id: str, new_station_id: str) -> None:
        if old_station_id == new_station_id:
            return

        updated_groups: list[dict[str, Any]] = []
        for group in self._groups:
            station_ids = []
            for station_id in group.get("stationIds", []):
                if station_id == old_station_id:
                    station_ids.append(new_station_id)
                else:
                    station_ids.append(station_id)
            updated_groups.append({**group, "stationIds": station_ids})
        self._options[CONF_GROUPS] = updated_groups

    def _remove_station_from_groups(self, station_id: str) -> None:
        updated_groups: list[dict[str, Any]] = []
        for group in self._groups:
            station_ids = [sid for sid in group.get("stationIds", []) if sid != station_id]
            updated_groups.append({**group, "stationIds": station_ids})
        self._options[CONF_GROUPS] = updated_groups

    def _parse_csv_list(self, raw: Any) -> list[str]:
        if not isinstance(raw, str) or raw.strip() == "":
            return []
        values = [value.strip() for value in raw.split(",") if value.strip() != ""]
        deduped: list[str] = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        return deduped

    def _station_ids_exist(self, station_ids: list[str]) -> bool:
        known = {charger.get("stationId") for charger in self._chargers}
        return all(station_id in known for station_id in station_ids)
