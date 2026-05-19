from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CitrineBridgeApiClient
from .const import CONF_BRIDGE_URL, CONF_POLL_SECONDS, CONF_SHARED_SECRET, DOMAIN
from .coordinator import CitrineCoordinator
from .services import async_register_services, async_unregister_services

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    bridge_url = entry.options.get(CONF_BRIDGE_URL, entry.data[CONF_BRIDGE_URL])
    shared_secret = entry.options.get(CONF_SHARED_SECRET, entry.data[CONF_SHARED_SECRET])
    poll_seconds = entry.options.get(CONF_POLL_SECONDS, entry.data.get(CONF_POLL_SECONDS, 30))

    client = CitrineBridgeApiClient(async_get_clientsession(hass), bridge_url, shared_secret)
    coordinator = CitrineCoordinator(hass, client, poll_seconds)
    await coordinator.async_config_entry_first_refresh()

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
