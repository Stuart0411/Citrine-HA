from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DEFAULT_CITRINEOS_OCPP16_PREFIX,
    DEFAULT_CITRINEOS_OCPP2_PREFIX,
    DEFAULT_STATION_DEFAULT_MAX_WATTS,
    DEFAULT_STATION_DEFAULT_PROTOCOL,
    DEFAULT_STATION_DEFAULT_TENANT_ID,
    DEFAULT_STATION_DEFAULT_WEIGHT,
    DEFAULT_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class CitrineApiError(HomeAssistantError):
    """Raised when the Citrine bridge request fails."""


class CitrineApiClient:
    async def get_health(self) -> dict[str, Any]:
        raise NotImplementedError()

    async def get_stations(self) -> list[dict[str, Any]]:
        raise NotImplementedError()

    async def get_state(self) -> dict[str, Any]:
        raise NotImplementedError()

    async def post_site_budget(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError()

    async def post_direct_limits(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError()

    async def post_reconcile(self) -> dict[str, Any]:
        raise NotImplementedError()

    async def post_remote_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError()

    async def post_remote_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError()

    async def post_set_availability(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError()


class CitrineBridgeApiClient(CitrineApiClient):
    def __init__(self, session: ClientSession, bridge_url: str, shared_secret: str) -> None:
        self._session = session
        self._bridge_url = bridge_url.rstrip("/")
        self._shared_secret = shared_secret

    async def get_health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def get_stations(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v1/stations")
        stations = payload.get("stations", [])
        if not isinstance(stations, list):
            raise CitrineApiError("Bridge stations response was not a list")
        return stations

    async def get_state(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/state")

    async def post_site_budget(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/policies/site-budget",
            json=payload,
            include_secret=True,
        )

    async def post_direct_limits(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/policies/direct-limits",
            json=payload,
            include_secret=True,
        )

    async def post_reconcile(self) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/policies/reconcile",
            include_secret=True,
        )

    async def post_remote_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/operations/remote-start",
            json=payload,
            include_secret=True,
        )

    async def post_remote_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/operations/remote-stop",
            json=payload,
            include_secret=True,
        )

    async def post_set_availability(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/operations/set-availability",
            json=payload,
            include_secret=True,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"accept": "application/json"}
        if include_secret:
            headers["x-shared-secret"] = self._shared_secret

        _LOGGER.debug("Bridge request %s %s", method, path)

        try:
            response = await self._session.request(
                method,
                f"{self._bridge_url}{path}",
                timeout=ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS),
                headers=headers,
                json=json,
            )
        except ClientError as err:
            _LOGGER.warning("Bridge request transport failure for %s: %s", path, err)
            raise CitrineApiError(f"Request failed for {path}: {err}") from err

        if response.status >= 400:
            body = await response.text()
            _LOGGER.warning(
                "Bridge request failed: %s %s status=%s body=%s",
                method,
                path,
                response.status,
                body,
            )
            raise CitrineApiError(
                f"Bridge request {method} {path} failed with status {response.status}: {body}"
            )

        try:
            return await response.json()
        except ValueError as err:
            body = await response.text()
            _LOGGER.warning("Bridge returned non-JSON for %s %s: %s", method, path, body)
            raise CitrineApiError(
                f"Bridge returned non-JSON response for {method} {path}: {body}"
            ) from err


class CitrineDirectApiClient(CitrineApiClient):
    def __init__(
        self,
        session: ClientSession,
        citrineos_base_url: str,
        *,
        stations_url: str | None = None,
        ocpp2_prefix: str = DEFAULT_CITRINEOS_OCPP2_PREFIX,
        ocpp16_prefix: str = DEFAULT_CITRINEOS_OCPP16_PREFIX,
        station_default_tenant_id: int = DEFAULT_STATION_DEFAULT_TENANT_ID,
        station_default_protocol: str = DEFAULT_STATION_DEFAULT_PROTOCOL,
        station_default_max_watts: int = DEFAULT_STATION_DEFAULT_MAX_WATTS,
        station_default_weight: int = DEFAULT_STATION_DEFAULT_WEIGHT,
    ) -> None:
        self._session = session
        self._base_url = citrineos_base_url.rstrip("/")
        self._user_stations_url = stations_url.rstrip("/") if isinstance(stations_url, str) and stations_url else None
        self._stations_url = self._user_stations_url or f"{self._base_url}/api/v1/charging-stations"
        self._ocpp2_prefix = ocpp2_prefix
        self._ocpp16_prefix = ocpp16_prefix
        self._station_default_tenant_id = station_default_tenant_id
        self._station_default_protocol = station_default_protocol
        self._station_default_max_watts = station_default_max_watts
        self._station_default_weight = station_default_weight
        self._stations_cache: list[dict[str, Any]] = []
        self._state: dict[str, Any] = {
            "runtime": {
                "effectiveLimits": [],
                "fallbackActive": False,
            },
            "outbox": [],
        }

    async def get_health(self) -> dict[str, Any]:
        # Direct mode does not require an intermediate bridge service.
        return {"status": "ok", "mode": "direct"}

    async def get_stations(self) -> list[dict[str, Any]]:
        attempted: list[str] = []
        last_error: str | None = None

        candidates = self._station_discovery_candidates()
        for candidate_url in candidates:
            attempted.append(candidate_url)
            try:
                response = await self._request("GET", candidate_url)
                payload = response.get("body", response)
                stations = self._normalize_discovered_stations(payload)
                self._stations_cache = stations
                self._stations_url = candidate_url
                _LOGGER.info("Direct mode discovered %s stations from %s", len(stations), candidate_url)
                return stations
            except CitrineApiError as err:
                last_error = str(err)
                # Route mismatch is common across CitrineOS deployments; try known alternatives.
                if "status 404" in last_error and not self._user_stations_url:
                    _LOGGER.debug("Station discovery route not found at %s; trying next candidate", candidate_url)
                    continue
                raise

        attempted_text = ", ".join(attempted)
        raise CitrineApiError(
            "Station discovery failed. "
            f"Tried: {attempted_text}. "
            f"Last error: {last_error or 'unknown'}. "
            "Set citrineos_stations_url to your actual CitrineOS station inventory endpoint."
        )

    def _station_discovery_candidates(self) -> list[str]:
        if self._user_stations_url:
            return [self._user_stations_url]

        return [
            f"{self._base_url}/api/v1/charging-stations",
            f"{self._base_url}/api/v1/stations",
            f"{self._base_url}/charging-stations",
            f"{self._base_url}/data/charging-stations",
        ]

    async def get_state(self) -> dict[str, Any]:
        return self._state

    async def post_site_budget(self, payload: dict[str, Any]) -> dict[str, Any]:
        stations = await self.get_stations()
        limits = self._allocate_site_budget(stations, payload)
        await self._dispatch_limits(limits)
        self._set_runtime(payload, limits)
        return {
            "message": "Direct policy accepted and applied.",
            "runtime": self._state["runtime"],
        }

    async def post_direct_limits(self, payload: dict[str, Any]) -> dict[str, Any]:
        stations = await self.get_stations()
        limits = self._allocate_direct_limits(stations, payload)
        await self._dispatch_limits(limits)
        self._set_runtime(payload, limits)
        return {
            "message": "Direct limits accepted and applied.",
            "runtime": self._state["runtime"],
        }

    async def post_reconcile(self) -> dict[str, Any]:
        desired = self._state.get("runtime", {}).get("desiredPolicy")
        if not isinstance(desired, dict):
            return {"message": "No desired policy to reconcile.", "runtime": self._state["runtime"]}

        policy = desired.get("policy")
        if not isinstance(policy, dict):
            return {"message": "No desired policy to reconcile.", "runtime": self._state["runtime"]}

        if policy.get("mode") == "direct-limits":
            return await self.post_direct_limits(policy)

        return await self.post_site_budget(policy)

    async def post_remote_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        station = await self._find_station(payload.get("stationId"))
        protocol = station["protocol"]
        station_id = station["stationId"]
        tenant_id = int(station["tenantId"])

        if protocol == "2.0.1":
            request_payload: dict[str, Any] = {
                "remoteStartId": payload.get("remoteStartId") or int(datetime.now(UTC).timestamp()),
                "idToken": {
                    "idToken": payload["idToken"],
                    "type": "Central",
                },
            }
            if "evseId" in payload:
                request_payload["evseId"] = payload["evseId"]

            result = await self._post_ocpp_action(
                protocol,
                station_id,
                tenant_id,
                "requestStartTransaction",
                request_payload,
            )
        else:
            request_payload = {
                "idTag": payload["idToken"],
                "connectorId": payload.get("connectorId") or station.get("connectorId") or 0,
            }
            result = await self._post_ocpp_action(
                protocol,
                station_id,
                tenant_id,
                "remoteStartTransaction",
                request_payload,
            )

        return {
            "message": "Remote start request dispatched.",
            "stationId": station_id,
            "protocol": protocol,
            "status": result["status"],
            "body": result["body"],
        }

    async def post_remote_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        station = await self._find_station(payload.get("stationId"))
        protocol = station["protocol"]
        station_id = station["stationId"]
        tenant_id = int(station["tenantId"])
        transaction_id = payload.get("transactionId")

        if protocol == "2.0.1":
            request_payload = {"transactionId": str(transaction_id)}
            result = await self._post_ocpp_action(
                protocol,
                station_id,
                tenant_id,
                "requestStopTransaction",
                request_payload,
            )
        else:
            numeric = int(transaction_id)
            request_payload = {"transactionId": numeric}
            result = await self._post_ocpp_action(
                protocol,
                station_id,
                tenant_id,
                "remoteStopTransaction",
                request_payload,
            )

        return {
            "message": "Remote stop request dispatched.",
            "stationId": station_id,
            "protocol": protocol,
            "status": result["status"],
            "body": result["body"],
        }

    async def post_set_availability(self, payload: dict[str, Any]) -> dict[str, Any]:
        station = await self._find_station(payload.get("stationId"))
        protocol = station["protocol"]
        station_id = station["stationId"]
        tenant_id = int(station["tenantId"])

        if protocol == "2.0.1":
            request_payload: dict[str, Any] = {
                "operationalStatus": payload["operationalStatus"],
            }
            evse_id = payload.get("evseId") or station.get("evseId")
            connector_id = payload.get("connectorId") or station.get("connectorId")
            if evse_id is not None:
                request_payload["evse"] = {"id": evse_id}
                if connector_id is not None:
                    request_payload["evse"]["connectorId"] = connector_id

            result = await self._post_ocpp_action(
                protocol,
                station_id,
                tenant_id,
                "changeAvailability",
                request_payload,
            )
        else:
            request_payload = {
                "connectorId": payload.get("connectorId") or station.get("connectorId") or 0,
                "type": payload["operationalStatus"],
            }
            result = await self._post_ocpp_action(
                protocol,
                station_id,
                tenant_id,
                "changeAvailability",
                request_payload,
            )

        return {
            "message": "Set availability request dispatched.",
            "stationId": station_id,
            "protocol": protocol,
            "status": result["status"],
            "body": result["body"],
        }

    async def _find_station(self, station_id: Any) -> dict[str, Any]:
        if not isinstance(station_id, str) or station_id == "":
            raise CitrineApiError("stationId is required")

        stations = await self.get_stations()
        for station in stations:
            if station.get("stationId") == station_id:
                return station

        raise CitrineApiError(f"Station {station_id} is not configured")

    def _policy_hash(self, payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _set_runtime(self, payload: dict[str, Any], limits: list[dict[str, Any]]) -> None:
        policy_hash = self._policy_hash(payload)
        now = datetime.now(UTC).isoformat()
        self._state["runtime"] = {
            "desiredPolicy": {
                "policy": payload,
                "receivedAt": now,
                "policyHash": policy_hash,
            },
            "effectiveLimits": limits,
            "fallbackActive": False,
            "lastAppliedAt": now,
        }

    async def _dispatch_limits(self, limits: list[dict[str, Any]]) -> None:
        for limit in limits:
            payload = self._translate_set_charging_profile(limit)
            await self._post_ocpp_action(
                limit["protocol"],
                limit["stationId"],
                int(limit["tenantId"]),
                "setChargingProfile",
                payload,
            )

    def _translate_set_charging_profile(self, limit: dict[str, Any]) -> dict[str, Any]:
        profile_id = max(1, int(datetime.now(UTC).timestamp()))
        max_watts = int(limit["maxWatts"])

        if limit["protocol"] == "2.0.1":
            return {
                "evseId": limit.get("evseId", 0),
                "chargingProfile": {
                    "id": profile_id,
                    "stackLevel": 10,
                    "chargingProfilePurpose": "ChargingStationMaxProfile",
                    "chargingProfileKind": "Absolute",
                    "chargingSchedule": [
                        {
                            "id": profile_id,
                            "chargingRateUnit": "W",
                            "chargingSchedulePeriod": [
                                {
                                    "startPeriod": 0,
                                    "limit": max_watts,
                                }
                            ],
                        }
                    ],
                },
            }

        return {
            "connectorId": limit.get("connectorId", 0),
            "csChargingProfiles": {
                "chargingProfileId": profile_id,
                "stackLevel": 10,
                "chargingProfilePurpose": "ChargePointMaxProfile",
                "chargingProfileKind": "Absolute",
                "chargingSchedule": {
                    "chargingRateUnit": "W",
                    "chargingSchedulePeriod": [
                        {
                            "startPeriod": 0,
                            "limit": max_watts,
                        }
                    ],
                },
            },
        }

    def _allocate_site_budget(
        self,
        stations: list[dict[str, Any]],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        override_map = {
            override.get("stationId"): override
            for override in payload.get("stationOverrides", [])
            if isinstance(override, dict)
        }
        weighted = [station for station in stations if float(station.get("weight", 0)) > 0]
        total_weight = sum(float(station.get("weight", 0)) for station in weighted)
        fallback_weight = total_weight if total_weight > 0 else (len(stations) or 1)
        budget = int(payload.get("siteBudgetWatts", 0))

        limits: list[dict[str, Any]] = []
        for station in stations:
            weight = float(station.get("weight", 0))
            shared_cap = int((budget * weight) // fallback_weight) if fallback_weight > 0 else 0
            explicit = override_map.get(station["stationId"], {}).get("maxWatts")
            computed = int(explicit) if explicit is not None else shared_cap
            max_watts = max(0, min(computed, int(station["maxWatts"])))

            limits.append(
                {
                    "stationId": station["stationId"],
                    "tenantId": station["tenantId"],
                    "protocol": station["protocol"],
                    "maxWatts": max_watts,
                    "evseId": station.get("evseId"),
                    "connectorId": station.get("connectorId"),
                }
            )

        return limits

    def _allocate_direct_limits(
        self,
        stations: list[dict[str, Any]],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        station_by_id = {station["stationId"]: station for station in stations}
        effective_by_station: dict[str, int] = {}
        group_membership: dict[str, set[str]] = {}

        for station in stations:
            for group_id in station.get("groupIds", []) or []:
                group_membership.setdefault(str(group_id), set()).add(station["stationId"])

        for group in payload.get("groups", []):
            if not isinstance(group, dict):
                continue
            group_id = group.get("groupId")
            if not isinstance(group_id, str):
                continue
            members = group_membership.setdefault(group_id, set())
            for station_id in group.get("stationIds", []) or []:
                if isinstance(station_id, str):
                    members.add(station_id)

        for group_limit in payload.get("groupLimits", []):
            if not isinstance(group_limit, dict):
                continue
            group_id = group_limit.get("groupId")
            if not isinstance(group_id, str):
                continue
            max_watts = int(group_limit.get("maxWatts", 0))
            member_ids = list(group_membership.get(group_id, set()))
            members = [station_by_id[sid] for sid in member_ids if sid in station_by_id]
            if not members:
                continue

            weighted = [m for m in members if float(m.get("weight", 0)) > 0]
            total_weight = sum(float(m.get("weight", 0)) for m in weighted)
            divisor = total_weight if total_weight > 0 else len(members)

            for station in members:
                if total_weight > 0:
                    raw = int((max_watts * float(station.get("weight", 0))) // divisor)
                else:
                    raw = int(max_watts // divisor)
                clamped = max(0, min(raw, int(station["maxWatts"])))
                existing = effective_by_station.get(station["stationId"])
                effective_by_station[station["stationId"]] = clamped if existing is None else min(existing, clamped)

        for station_limit in payload.get("stationLimits", []):
            if not isinstance(station_limit, dict):
                continue
            station_id = station_limit.get("stationId")
            if not isinstance(station_id, str) or station_id not in station_by_id:
                continue
            station = station_by_id[station_id]
            clamped = max(0, min(int(station_limit.get("maxWatts", 0)), int(station["maxWatts"])))
            effective_by_station[station_id] = clamped

        default_unspecified = payload.get("defaultUnspecifiedWatts")

        limits: list[dict[str, Any]] = []
        for station in stations:
            if default_unspecified is None:
                fallback = int(station["maxWatts"])
            else:
                fallback = max(0, min(int(default_unspecified), int(station["maxWatts"])))
            max_watts = effective_by_station.get(station["stationId"], fallback)

            limits.append(
                {
                    "stationId": station["stationId"],
                    "tenantId": station["tenantId"],
                    "protocol": station["protocol"],
                    "maxWatts": max_watts,
                    "evseId": station.get("evseId"),
                    "connectorId": station.get("connectorId"),
                }
            )

        return limits

    async def _post_ocpp_action(
        self,
        protocol: str,
        station_id: str,
        tenant_id: int,
        action_path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        version = "2.0.1" if protocol == "2.0.1" else "1.6"
        prefix = self._ocpp2_prefix if version == "2.0.1" else self._ocpp16_prefix
        endpoint = f"{self._base_url}/ocpp/{version}/{prefix}/{action_path}"
        params = {
            "identifier": station_id,
            "tenantId": str(tenant_id),
        }
        _LOGGER.debug(
            "Direct OCPP action %s version=%s station=%s tenant=%s",
            action_path,
            version,
            station_id,
            tenant_id,
        )
        return await self._request("POST", endpoint, params=params, json_payload=payload)

    def _normalize_discovered_stations(self, data: Any) -> list[dict[str, Any]]:
        station_list: list[Any] = []

        if isinstance(data, list):
            station_list = data
        elif isinstance(data, dict):
            for key in ("stations", "data", "results"):
                candidate = data.get(key)
                if isinstance(candidate, list):
                    station_list = candidate
                    break

        stations: list[dict[str, Any]] = []
        for item in station_list:
            if not isinstance(item, dict):
                continue

            station_id = self._read_text(item, ["stationId", "identifier", "chargePointId", "id"])
            if not station_id:
                continue

            protocol = self._parse_protocol(
                self._read_text(item, ["protocol", "ocppVersion", "ocppProtocol"])
            ) or self._station_default_protocol

            tenant_id = self._read_number(item, ["tenantId", "tenant"]) or self._station_default_tenant_id
            max_watts = self._read_number(item, ["maxWatts", "maxPowerWatts"]) or self._station_default_max_watts
            weight = self._read_number(item, ["weight"]) or self._station_default_weight
            evse_id = self._read_number(item, ["evseId"])
            connector_id = self._read_number(item, ["connectorId"])
            group_ids_raw = item.get("groupIds")
            group_ids = [str(group) for group in group_ids_raw] if isinstance(group_ids_raw, list) else []

            stations.append(
                {
                    "stationId": station_id,
                    "protocol": protocol,
                    "tenantId": int(tenant_id),
                    "maxWatts": int(max_watts),
                    "weight": int(weight),
                    "groupIds": group_ids,
                    "evseId": int(evse_id) if evse_id is not None else None,
                    "connectorId": int(connector_id) if connector_id is not None else None,
                }
            )

        return stations

    def _parse_protocol(self, value: str | None) -> str | None:
        if value in ("2.0.1", "1.6"):
            return value
        if not isinstance(value, str):
            return None
        if "2.0.1" in value:
            return "2.0.1"
        if "1.6" in value:
            return "1.6"
        return None

    def _read_number(self, item: dict[str, Any], keys: list[str]) -> int | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        return None

    def _read_text(self, item: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip() != "":
                return value
        return None

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"accept": "application/json"}
        if json_payload is not None:
            headers["content-type"] = "application/json"

        _LOGGER.debug("Direct request %s %s", method, url)

        try:
            response = await self._session.request(
                method,
                url,
                params=params,
                timeout=ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS),
                headers=headers,
                json=json_payload,
            )
        except ClientError as err:
            _LOGGER.warning("Direct request transport failure for %s: %s", url, err)
            raise CitrineApiError(f"Direct request failed for {url}: {err}") from err

        if response.status >= 400:
            body = await response.text()
            _LOGGER.warning(
                "Direct request failed: %s %s status=%s body=%s",
                method,
                url,
                response.status,
                body,
            )
            raise CitrineApiError(
                f"Direct request {method} {url} failed with status {response.status}: {body}"
            )

        try:
            body_json = await response.json()
        except ValueError:
            body_text = await response.text()
            return {"status": response.status, "ok": response.status < 400, "body": body_text}

        # Preserve the raw response in operations while still returning dict payloads.
        if isinstance(body_json, dict) and "status" in body_json and "body" in body_json:
            return body_json

        return {
            "status": response.status,
            "ok": response.status < 400,
            "body": body_json,
            **(body_json if isinstance(body_json, dict) else {}),
        }
