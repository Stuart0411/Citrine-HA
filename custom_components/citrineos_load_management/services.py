from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    DOMAIN,
    SERVICE_APPLY_DIRECT_LIMITS,
    SERVICE_APPLY_SITE_BUDGET,
    SERVICE_RECONCILE,
    SERVICE_REMOTE_START_TRANSACTION,
    SERVICE_REMOTE_STOP_TRANSACTION,
    SERVICE_SET_AVAILABILITY,
)

_LOGGER = logging.getLogger(__name__)

SITE_BUDGET_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("idempotency_key"): cv.string,
        vol.Optional("source_timestamp"): cv.string,
        vol.Optional("ttl_seconds", default=120): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
        vol.Required("site_budget_watts"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("station_overrides", default=[]): list,
    }
)

DIRECT_LIMITS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("idempotency_key"): cv.string,
        vol.Optional("source_timestamp"): cv.string,
        vol.Optional("ttl_seconds", default=120): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
        vol.Optional("station_limits", default=[]): list,
        vol.Optional("groups", default=[]): list,
        vol.Optional("group_limits", default=[]): list,
        vol.Optional("default_unspecified_watts"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)

RECONCILE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)

REMOTE_START_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required("station_id"): cv.string,
        vol.Required("id_token"): cv.string,
        vol.Optional("evse_id"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("connector_id"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("remote_start_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

REMOTE_STOP_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required("station_id"): cv.string,
        vol.Optional("transaction_id"): vol.Any(cv.string, vol.All(vol.Coerce(int), vol.Range(min=0))),
    }
)

SET_AVAILABILITY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required("station_id"): cv.string,
        vol.Required("operational_status"): vol.In(["Operative", "Inoperative"]),
        vol.Optional("evse_id"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("connector_id"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_entry(hass: HomeAssistant, service_call: ServiceCall) -> ConfigEntry:
    domain_entries = hass.config_entries.async_entries(DOMAIN)
    if not domain_entries:
        raise HomeAssistantError("No CitrineOS Load Management config entries are loaded")

    requested_id = service_call.data.get(ATTR_CONFIG_ENTRY_ID)
    if requested_id:
        for entry in domain_entries:
            if entry.entry_id == requested_id:
                return entry
        raise HomeAssistantError(f"Config entry {requested_id} was not found")

    if len(domain_entries) > 1:
        raise HomeAssistantError(
            "Multiple config entries exist. Provide config_entry_id in service data."
        )

    return domain_entries[0]


def _normalize_station_overrides(raw: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        station_id = item.get("stationId") or item.get("station_id")
        if not station_id:
            continue

        payload: dict[str, Any] = {"stationId": station_id}
        if "maxWatts" in item:
            payload["maxWatts"] = item["maxWatts"]
        elif "max_watts" in item:
            payload["maxWatts"] = item["max_watts"]

        normalized.append(payload)

    return normalized


def _normalize_list_payload(raw: list[Any], key_map: dict[str, str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        output: dict[str, Any] = {}
        for source_key, target_key in key_map.items():
            if source_key in item:
                output[target_key] = item[source_key]
        if output:
            normalized.append(output)

    return normalized


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_APPLY_SITE_BUDGET):
        return

    async def handle_site_budget(service_call: ServiceCall) -> None:
        entry = _resolve_entry(hass, service_call)
        client = hass.data[DOMAIN][entry.entry_id]["client"]

        payload = {
            "mode": "site-budget",
            "idempotencyKey": service_call.data.get("idempotency_key") or f"ha-{datetime.now(UTC).timestamp()}",
            "sourceTimestamp": service_call.data.get("source_timestamp") or _now_iso(),
            "ttlSeconds": service_call.data["ttl_seconds"],
            "siteBudgetWatts": service_call.data["site_budget_watts"],
            "stationOverrides": _normalize_station_overrides(service_call.data.get("station_overrides", [])),
        }

        await client.post_site_budget(payload)
        _LOGGER.info("Applied site budget policy for entry %s", entry.entry_id)
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()

    async def handle_direct_limits(service_call: ServiceCall) -> None:
        entry = _resolve_entry(hass, service_call)
        client = hass.data[DOMAIN][entry.entry_id]["client"]

        station_limits = _normalize_list_payload(
            service_call.data.get("station_limits", []),
            {
                "stationId": "stationId",
                "station_id": "stationId",
                "maxWatts": "maxWatts",
                "max_watts": "maxWatts",
            },
        )
        groups = _normalize_list_payload(
            service_call.data.get("groups", []),
            {
                "groupId": "groupId",
                "group_id": "groupId",
                "stationIds": "stationIds",
                "station_ids": "stationIds",
            },
        )
        group_limits = _normalize_list_payload(
            service_call.data.get("group_limits", []),
            {
                "groupId": "groupId",
                "group_id": "groupId",
                "maxWatts": "maxWatts",
                "max_watts": "maxWatts",
            },
        )

        payload: dict[str, Any] = {
            "mode": "direct-limits",
            "idempotencyKey": service_call.data.get("idempotency_key") or f"ha-{datetime.now(UTC).timestamp()}",
            "sourceTimestamp": service_call.data.get("source_timestamp") or _now_iso(),
            "ttlSeconds": service_call.data["ttl_seconds"],
            "stationLimits": station_limits,
            "groups": groups,
            "groupLimits": group_limits,
        }

        if "default_unspecified_watts" in service_call.data:
            payload["defaultUnspecifiedWatts"] = service_call.data["default_unspecified_watts"]

        await client.post_direct_limits(payload)
        _LOGGER.info("Applied direct limits policy for entry %s", entry.entry_id)
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()

    async def handle_reconcile(service_call: ServiceCall) -> None:
        entry = _resolve_entry(hass, service_call)
        client = hass.data[DOMAIN][entry.entry_id]["client"]

        await client.post_reconcile()
        _LOGGER.info("Triggered reconcile for entry %s", entry.entry_id)
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()

    async def handle_remote_start(service_call: ServiceCall) -> None:
        entry = _resolve_entry(hass, service_call)
        client = hass.data[DOMAIN][entry.entry_id]["client"]

        payload: dict[str, Any] = {
            "stationId": service_call.data["station_id"],
            "idToken": service_call.data["id_token"],
        }

        if "evse_id" in service_call.data:
            payload["evseId"] = service_call.data["evse_id"]
        if "connector_id" in service_call.data:
            payload["connectorId"] = service_call.data["connector_id"]
        if "remote_start_id" in service_call.data:
            payload["remoteStartId"] = service_call.data["remote_start_id"]

        result = await client.post_remote_start(payload)
        transaction_id = result.get("transactionId") if isinstance(result, dict) else None
        _LOGGER.info(
            "Remote start dispatched for station %s transaction_id=%s (entry %s)",
            payload["stationId"],
            transaction_id,
            entry.entry_id,
        )
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()

    async def handle_remote_stop(service_call: ServiceCall) -> None:
        entry = _resolve_entry(hass, service_call)
        client = hass.data[DOMAIN][entry.entry_id]["client"]

        payload: dict[str, Any] = {
            "stationId": service_call.data["station_id"],
        }
        if "transaction_id" in service_call.data:
            payload["transactionId"] = service_call.data["transaction_id"]

        result = await client.post_remote_stop(payload)
        transaction_id = result.get("transactionId") if isinstance(result, dict) else payload.get("transactionId")
        _LOGGER.info(
            "Remote stop dispatched for station %s transaction_id=%s (entry %s)",
            payload["stationId"],
            transaction_id,
            entry.entry_id,
        )
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()

    async def handle_set_availability(service_call: ServiceCall) -> None:
        entry = _resolve_entry(hass, service_call)
        client = hass.data[DOMAIN][entry.entry_id]["client"]

        payload: dict[str, Any] = {
            "stationId": service_call.data["station_id"],
            "operationalStatus": service_call.data["operational_status"],
        }

        if "evse_id" in service_call.data:
            payload["evseId"] = service_call.data["evse_id"]
        if "connector_id" in service_call.data:
            payload["connectorId"] = service_call.data["connector_id"]

        await client.post_set_availability(payload)
        _LOGGER.info(
            "Set availability dispatched for station %s status=%s (entry %s)",
            payload["stationId"],
            payload["operationalStatus"],
            entry.entry_id,
        )
        await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_SITE_BUDGET,
        handle_site_budget,
        schema=SITE_BUDGET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_DIRECT_LIMITS,
        handle_direct_limits,
        schema=DIRECT_LIMITS_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RECONCILE,
        handle_reconcile,
        schema=RECONCILE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOTE_START_TRANSACTION,
        handle_remote_start,
        schema=REMOTE_START_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOTE_STOP_TRANSACTION,
        handle_remote_stop,
        schema=REMOTE_STOP_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AVAILABILITY,
        handle_set_availability,
        schema=SET_AVAILABILITY_SCHEMA,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_APPLY_SITE_BUDGET):
        hass.services.async_remove(DOMAIN, SERVICE_APPLY_SITE_BUDGET)
    if hass.services.has_service(DOMAIN, SERVICE_APPLY_DIRECT_LIMITS):
        hass.services.async_remove(DOMAIN, SERVICE_APPLY_DIRECT_LIMITS)
    if hass.services.has_service(DOMAIN, SERVICE_RECONCILE):
        hass.services.async_remove(DOMAIN, SERVICE_RECONCILE)
    if hass.services.has_service(DOMAIN, SERVICE_REMOTE_START_TRANSACTION):
        hass.services.async_remove(DOMAIN, SERVICE_REMOTE_START_TRANSACTION)
    if hass.services.has_service(DOMAIN, SERVICE_REMOTE_STOP_TRANSACTION):
        hass.services.async_remove(DOMAIN, SERVICE_REMOTE_STOP_TRANSACTION)
    if hass.services.has_service(DOMAIN, SERVICE_SET_AVAILABILITY):
        hass.services.async_remove(DOMAIN, SERVICE_SET_AVAILABILITY)
