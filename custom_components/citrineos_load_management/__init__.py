from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CitrineBridgeApiClient, CitrineDirectApiClient
from .const import (
    CONF_BRIDGE_URL,
    CONF_CITRINEOS_BASE_URL,
    CONF_CITRINEOS_OCPP16_PREFIX,
    CONF_CITRINEOS_OCPP2_PREFIX,
    CONF_CITRINEOS_STATIONS_URL,
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
    DEFAULT_STATION_DEFAULT_MAX_WATTS,
    DEFAULT_STATION_DEFAULT_PROTOCOL,
    DEFAULT_STATION_DEFAULT_TENANT_ID,
    DEFAULT_STATION_DEFAULT_WEIGHT,
    DOMAIN,
    MODE_BRIDGE,
    MODE_DIRECT,
)
from .coordinator import CitrineCoordinator
from .services import async_register_services, async_unregister_services

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    mode = entry.options.get(CONF_MODE, entry.data.get(CONF_MODE, MODE_BRIDGE))
    poll_seconds = entry.options.get(CONF_POLL_SECONDS, entry.data.get(CONF_POLL_SECONDS, 30))
    session = async_get_clientsession(hass)

    if mode == MODE_DIRECT:
        _LOGGER.info("Setting up CitrineOS Load Management in direct mode")
        client = CitrineDirectApiClient(
            session,
            entry.options.get(CONF_CITRINEOS_BASE_URL, entry.data[CONF_CITRINEOS_BASE_URL]),
            stations_url=entry.options.get(
                CONF_CITRINEOS_STATIONS_URL,
                entry.data.get(CONF_CITRINEOS_STATIONS_URL),
            ),
            manual_stations_json=entry.options.get(
                CONF_MANUAL_STATIONS_JSON,
                entry.data.get(CONF_MANUAL_STATIONS_JSON),
            ),
            ocpp2_prefix=entry.options.get(
                CONF_CITRINEOS_OCPP2_PREFIX,
                entry.data.get(CONF_CITRINEOS_OCPP2_PREFIX, DEFAULT_CITRINEOS_OCPP2_PREFIX),
            ),
            ocpp16_prefix=entry.options.get(
                CONF_CITRINEOS_OCPP16_PREFIX,
                entry.data.get(CONF_CITRINEOS_OCPP16_PREFIX, DEFAULT_CITRINEOS_OCPP16_PREFIX),
            ),
            station_default_tenant_id=entry.options.get(
                CONF_STATION_DEFAULT_TENANT_ID,
                entry.data.get(CONF_STATION_DEFAULT_TENANT_ID, DEFAULT_STATION_DEFAULT_TENANT_ID),
            ),
            station_default_protocol=entry.options.get(
                CONF_STATION_DEFAULT_PROTOCOL,
                entry.data.get(CONF_STATION_DEFAULT_PROTOCOL, DEFAULT_STATION_DEFAULT_PROTOCOL),
            ),
            station_default_max_watts=entry.options.get(
                CONF_STATION_DEFAULT_MAX_WATTS,
                entry.data.get(CONF_STATION_DEFAULT_MAX_WATTS, DEFAULT_STATION_DEFAULT_MAX_WATTS),
            ),
            station_default_weight=entry.options.get(
                CONF_STATION_DEFAULT_WEIGHT,
                entry.data.get(CONF_STATION_DEFAULT_WEIGHT, DEFAULT_STATION_DEFAULT_WEIGHT),
            ),
        )
    else:
        bridge_url = entry.options.get(CONF_BRIDGE_URL, entry.data[CONF_BRIDGE_URL])
        shared_secret = entry.options.get(CONF_SHARED_SECRET, entry.data[CONF_SHARED_SECRET])
        _LOGGER.info("Setting up CitrineOS Load Management in bridge mode for %s", bridge_url)
        client = CitrineBridgeApiClient(session, bridge_url, shared_secret)

    coordinator = CitrineCoordinator(hass, client, poll_seconds)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.exception("Initial coordinator refresh failed during setup")
        raise

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    if not hass.data[DOMAIN]:
        await async_unregister_services(hass)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
