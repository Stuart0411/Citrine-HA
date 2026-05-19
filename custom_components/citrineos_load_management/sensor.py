from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CitrineCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CitrineCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = [
        CitrineStationCountSensor(entry.entry_id, coordinator),
        CitrineFallbackActiveSensor(entry.entry_id, coordinator),
    ]

    known_station_ids: set[str] = set()

    def build_station_entities() -> list[SensorEntity]:
        station_entities: list[SensorEntity] = []
        stations = coordinator.data.get("stations", []) if coordinator.data else []
        for station in stations:
            if not isinstance(station, dict):
                continue
            station_id = station.get("stationId")
            if not station_id or station_id in known_station_ids:
                continue
            known_station_ids.add(station_id)
            station_entities.append(
                CitrineStationLimitSensor(entry.entry_id, coordinator, station_id)
            )
        return station_entities

    entities.extend(build_station_entities())
    async_add_entities(entities)

    @callback
    def _handle_coordinator_update() -> None:
        new_entities = build_station_entities()
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


class CitrineBaseCoordinatorSensor(CoordinatorEntity[CitrineCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry_id: str, coordinator: CitrineCoordinator) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id


class CitrineStationCountSensor(CitrineBaseCoordinatorSensor):
    _attr_translation_key = "station_count"
    _attr_icon = "mdi:ev-station"

    def __init__(self, entry_id: str, coordinator: CitrineCoordinator) -> None:
        super().__init__(entry_id, coordinator)
        self._attr_unique_id = f"{entry_id}_station_count"

    @property
    def native_value(self) -> int:
        stations = self.coordinator.data.get("stations", []) if self.coordinator.data else []
        return len(stations)


class CitrineFallbackActiveSensor(CitrineBaseCoordinatorSensor):
    _attr_translation_key = "fallback_active"
    _attr_icon = "mdi:alert-outline"

    def __init__(self, entry_id: str, coordinator: CitrineCoordinator) -> None:
        super().__init__(entry_id, coordinator)
        self._attr_unique_id = f"{entry_id}_fallback_active"

    @property
    def native_value(self) -> bool:
        runtime = self._runtime
        return bool(runtime.get("fallbackActive", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        runtime = self._runtime
        reason = runtime.get("fallbackReason")
        if reason:
            return {"fallback_reason": reason}
        return None

    @property
    def _runtime(self) -> dict[str, Any]:
        state = self.coordinator.data.get("state", {}) if self.coordinator.data else {}
        runtime = state.get("runtime", {})
        return runtime if isinstance(runtime, dict) else {}


class CitrineStationLimitSensor(CitrineBaseCoordinatorSensor):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry_id: str, coordinator: CitrineCoordinator, station_id: str) -> None:
        super().__init__(entry_id, coordinator)
        self._station_id = station_id
        self._attr_unique_id = f"{entry_id}_{station_id}_effective_limit_watts"
        self._attr_name = f"{station_id} Effective Limit"

    @property
    def native_value(self) -> int | None:
        for limit in self._effective_limits:
            if limit.get("stationId") == self._station_id:
                watts = limit.get("maxWatts")
                if isinstance(watts, (int, float)):
                    return int(watts)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        for limit in self._effective_limits:
            if limit.get("stationId") == self._station_id:
                attrs: dict[str, Any] = {
                    "station_id": self._station_id,
                    "protocol": limit.get("protocol"),
                    "tenant_id": limit.get("tenantId"),
                }
                if "evseId" in limit:
                    attrs["evse_id"] = limit.get("evseId")
                if "connectorId" in limit:
                    attrs["connector_id"] = limit.get("connectorId")
                return attrs
        return {"station_id": self._station_id}

    @property
    def _effective_limits(self) -> list[dict[str, Any]]:
        state = self.coordinator.data.get("state", {}) if self.coordinator.data else {}
        runtime = state.get("runtime", {}) if isinstance(state, dict) else {}
        limits = runtime.get("effectiveLimits", []) if isinstance(runtime, dict) else []
        return [item for item in limits if isinstance(item, dict)]
