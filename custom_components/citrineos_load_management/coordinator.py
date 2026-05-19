from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CitrineApiClient, CitrineApiError
from .const import DEFAULT_POLL_SECONDS

_LOGGER = logging.getLogger(__name__)


class CitrineCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: CitrineApiClient,
        poll_seconds: int = DEFAULT_POLL_SECONDS,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="CitrineOS Load Management",
            update_interval=timedelta(seconds=poll_seconds),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            stations = await self.client.get_stations()
            state = await self.client.get_state()
        except CitrineApiError as err:
            raise UpdateFailed(str(err)) from err

        return {
            "stations": stations,
            "state": state,
        }
