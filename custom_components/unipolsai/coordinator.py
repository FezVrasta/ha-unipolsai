"""Data coordinators for the UnipolSai Unibox integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UnipolSaiApi, UnipolSaiAuthError, UnipolSaiError
from .const import (
    DOMAIN,
    REFRESH_POLL_INTERVAL,
    REFRESH_TIMEOUT,
    SCAN_INTERVAL,
    USAGE_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class UnipolSaiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls position and service status.

    Both calls are free: lastPosition only spends quota when update=true, and
    vehicleVAS never does. So this can run on a normal interval.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: UnipolSaiApi,
        plate: str,
        vehicle: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {plate}",
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.api = api
        self.plate = plate
        self.vehicle = vehicle
        self._refreshing = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            position, vas = await asyncio.gather(
                self.api.last_position(self.plate),
                self.api.vehicle_vas(self.plate),
            )
        except UnipolSaiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UnipolSaiError as err:
            raise UpdateFailed(str(err)) from err
        return {"position": position, "vas": vas}

    @property
    def refresh_in_progress(self) -> bool:
        return self._refreshing

    async def async_force_refresh(self) -> None:
        """Ask the box for a fresh fix, then wait for the cycle to resolve.

        Measured behaviour: the update=true response carries the *old*
        position, pendingRequest goes true a few seconds later, and the whole
        thing settles after about five minutes. It can settle without the
        position changing, which is what a parked car with the engine off
        looks like. A failed fix costs no quota.
        """
        if self._refreshing:
            raise HomeAssistantError("A position refresh is already running")

        quota = (self.data or {}).get("position", {}).get("dailyFruitions") or {}
        current, maximum = quota.get("current"), quota.get("max")
        if current is not None and maximum is not None and current >= maximum:
            raise HomeAssistantError(
                f"Daily position-refresh quota used up ({current}/{maximum}). "
                "It resets tomorrow."
            )

        before = (self.data or {}).get("position", {}).get("date")
        self._refreshing = True
        self.async_update_listeners()
        try:
            await self.api.last_position(self.plate, update=True)

            waited = 0
            settled = False
            while waited < REFRESH_TIMEOUT:
                await asyncio.sleep(REFRESH_POLL_INTERVAL)
                waited += REFRESH_POLL_INTERVAL
                position = await self.api.last_position(self.plate)
                self.async_set_updated_data(
                    {**(self.data or {}), "position": position}
                )
                if position.get("date") != before:
                    _LOGGER.debug("Fresh fix for %s after %ss", self.plate, waited)
                    return
                if position.get("pendingRequest"):
                    settled = False
                elif settled:
                    # Two consecutive not-pending reads with an unchanged
                    # timestamp: the box never answered.
                    break
                else:
                    settled = True

            _LOGGER.warning(
                "Position refresh for %s finished without a new fix. The box "
                "does not answer when the engine is off.",
                self.plate,
            )
        except UnipolSaiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UnipolSaiError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            self._refreshing = False
            self.async_update_listeners()


class UnipolSaiUsageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls driving statistics. Free, and only changes daily."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: UnipolSaiApi,
        plate: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {plate} usage",
            update_interval=USAGE_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.api = api
        self.plate = plate

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.vehicle_usages(self.plate)
        except UnipolSaiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UnipolSaiError as err:
            raise UpdateFailed(str(err)) from err
