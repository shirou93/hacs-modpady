"""Polling coordinator for mOdpady schedules."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ModpadyApiError, async_get_schedule
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ModpadyCoordinator(DataUpdateCoordinator[dict]):
    """Fetch and normalize the schedule for one configured address."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.config_entry = entry
        self._refresh_settings()
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=self.scan_interval_minutes),
        )

    def _refresh_settings(self) -> None:
        self.settings = {**self.config_entry.data, **self.config_entry.options}
        self.scan_interval_minutes = int(
            self.settings.get("update_interval", DEFAULT_SCAN_INTERVAL)
        )

    async def _async_update_data(self) -> dict:
        self._refresh_settings()
        try:
            return await async_get_schedule(
                self.hass,
                self.settings["city"],
                self.settings["locality_id"],
                self.settings.get("street_id", ""),
                self.settings["address"],
            )
        except ModpadyApiError as err:
            raise UpdateFailed(f"Nie można pobrać harmonogramu: {err}") from err

