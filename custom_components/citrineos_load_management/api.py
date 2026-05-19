from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.exceptions import HomeAssistantError

from .const import DEFAULT_TIMEOUT_SECONDS


class CitrineApiError(HomeAssistantError):
    """Raised when the Citrine bridge request fails."""


class CitrineBridgeApiClient:
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

        try:
            response = await self._session.request(
                method,
                f"{self._bridge_url}{path}",
                timeout=ClientTimeout(total=DEFAULT_TIMEOUT_SECONDS),
                headers=headers,
                json=json,
            )
        except ClientError as err:
            raise CitrineApiError(f"Request failed for {path}: {err}") from err

        if response.status >= 400:
            body = await response.text()
            raise CitrineApiError(
                f"Bridge request {method} {path} failed with status {response.status}: {body}"
            )

        try:
            return await response.json()
        except ValueError as err:
            body = await response.text()
            raise CitrineApiError(
                f"Bridge returned non-JSON response for {method} {path}: {body}"
            ) from err
