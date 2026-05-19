from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CitrineBridgeApiClient
from .const import DOMAIN
from .coordinator import CitrineCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CitrineCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client: CitrineBridgeApiClient = hass.data[DOMAIN][entry.entry_id]["client"]

    known_station_ids: set[str] = set()

    def build_station_buttons() -> list[ButtonEntity]:
        buttons: list[ButtonEntity] = []
        stations = coordinator.data.get("stations", []) if coordinator.data else []

        for station in stations:
            if not isinstance(station, dict):
                continue

            station_id = station.get("stationId")
            if not isinstance(station_id, str) or station_id in known_station_ids:
                continue

            known_station_ids.add(station_id)
            buttons.extend(
                [
                    CitrineRemoteStartButton(entry.entry_id, coordinator, client, station_id),
                    CitrineSetOperativeButton(entry.entry_id, coordinator, client, station_id),
                    CitrineSetInoperativeButton(entry.entry_id, coordinator, client, station_id),
                ]
            )

        return buttons

    entities = build_station_buttons()
    if entities:
        async_add_entities(entities)

    @callback
    def _handle_coordinator_update() -> None:
        new_buttons = build_station_buttons()
        if new_buttons:
            async_add_entities(new_buttons)

    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


class CitrineStationActionButton(CoordinatorEntity[CitrineCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        coordinator: CitrineCoordinator,
        client: CitrineBridgeApiClient,
        station_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._station_id = station_id
        self._client = client

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "station_id": self._station_id,
        }


class CitrineRemoteStartButton(CitrineStationActionButton):
    _attr_icon = "mdi:play-circle-outline"

    def __init__(
        self,
        entry_id: str,
        coordinator: CitrineCoordinator,
        client: CitrineBridgeApiClient,
        station_id: str,
    ) -> None:
        super().__init__(entry_id, coordinator, client, station_id)
        self._attr_unique_id = f"{entry_id}_{station_id}_remote_start"
        self._attr_name = f"{station_id} Remote Start"

    async def async_press(self) -> None:
        # Deterministic id token avoids storing secrets in entity state while enabling one-tap start.
        payload = {
            "stationId": self._station_id,
            "idToken": f"HA-{self._station_id}",
        }
        await self._client.post_remote_start(payload)
        await self.coordinator.async_request_refresh()


class CitrineSetOperativeButton(CitrineStationActionButton):
    _attr_icon = "mdi:power-plug"

    def __init__(
        self,
        entry_id: str,
        coordinator: CitrineCoordinator,
        client: CitrineBridgeApiClient,
        station_id: str,
    ) -> None:
        super().__init__(entry_id, coordinator, client, station_id)
        self._attr_unique_id = f"{entry_id}_{station_id}_set_operative"
        self._attr_name = f"{station_id} Set Operative"

    async def async_press(self) -> None:
        payload = {
            "stationId": self._station_id,
            "operationalStatus": "Operative",
        }
        await self._client.post_set_availability(payload)
        await self.coordinator.async_request_refresh()


class CitrineSetInoperativeButton(CitrineStationActionButton):
    _attr_icon = "mdi:power-plug-off"

    def __init__(
        self,
        entry_id: str,
        coordinator: CitrineCoordinator,
        client: CitrineBridgeApiClient,
        station_id: str,
    ) -> None:
        super().__init__(entry_id, coordinator, client, station_id)
        self._attr_unique_id = f"{entry_id}_{station_id}_set_inoperative"
        self._attr_name = f"{station_id} Set Inoperative"

    async def async_press(self) -> None:
        payload = {
            "stationId": self._station_id,
            "operationalStatus": "Inoperative",
        }
        await self._client.post_set_availability(payload)
        await self.coordinator.async_request_refresh()
