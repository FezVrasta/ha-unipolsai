"""Update coordinators."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pyunipolsai import (
    ALERT_SERVICES,
    Notification,
    Position,
    Service,
    UnipolSaiAuthError,
    UnipolSaiClient,
    UnipolSaiError,
    UsageStats,
    Vehicle,
)

from .const import (
    DOMAIN,
    REFRESH_POLL_INTERVAL,
    REFRESH_TIMEOUT,
    SCAN_INTERVAL,
    USAGE_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class VehicleData:
    """Everything the cheap poll returns for one vehicle."""

    position: Position
    services: dict[str, Service]
    notifications: dict[str, list[Notification]] = field(default_factory=dict)

    def service_active(self, name: str) -> bool:
        """Whether a value-added service is switched on for this contract."""
        service = self.services.get(name)
        return bool(service and service.activated)

    def latest(self, service: str) -> Notification | None:
        """Most recent alert event for one service, if any."""
        events = self.notifications.get(service) or []
        return events[0] if events else None


class UnipolSaiUniboxCoordinator(DataUpdateCoordinator[VehicleData]):
    """Polls position, service status and alerts for one vehicle.

    Everything here is free: only a forced refresh spends quota, and that is
    driven by the button, never by this loop.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: UnipolSaiClient,
        vehicle: Vehicle,
    ) -> None:
        """Set up the per-vehicle coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {vehicle.plate}",
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self.vehicle = vehicle
        self._refreshing = False

    async def _async_update_data(self) -> VehicleData:
        try:
            position, services = await asyncio.gather(
                self.client.async_get_position(self.vehicle),
                self.client.async_get_services(self.vehicle),
            )
            # Only ask about alerts the contract actually has switched on.
            active = [
                name
                for name in ALERT_SERVICES
                if (svc := services.get(name)) and svc.activated
            ]
            results = await asyncio.gather(
                *(
                    self.client.async_get_notifications(self.vehicle, name)
                    for name in active
                ),
                return_exceptions=True,
            )
        except UnipolSaiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UnipolSaiError as err:
            raise UpdateFailed(str(err)) from err

        previous = self.data.notifications if self.data else {}
        notifications: dict[str, list[Notification]] = {}
        for name, result in zip(active, results, strict=True):
            if isinstance(result, BaseException):
                # One flaky alert endpoint should not take the position with it.
                _LOGGER.debug("Alerts for %s unavailable: %s", name, result)
                notifications[name] = previous.get(name, [])
            else:
                notifications[name] = result

        return VehicleData(
            position=position, services=services, notifications=notifications
        )

    @property
    def refresh_in_progress(self) -> bool:
        """Whether a forced refresh is currently running."""
        return self._refreshing

    async def async_force_refresh(self) -> None:
        """Ask the box for a fresh fix and wait out the cycle.

        Measured behaviour: the request returns immediately with the *old*
        position, the pending flag goes true a few seconds later, and the
        whole thing settles after about five minutes. It can settle without
        the position changing, which is what a car parked with the engine off
        looks like — and that costs no quota. So success is "the timestamp
        moved", not "the flag cleared".
        """
        if self._refreshing:
            raise HomeAssistantError("A position refresh is already running")

        quota = self.data.position.quota if self.data else None
        if quota and quota.exhausted:
            raise HomeAssistantError(
                f"Daily position-refresh quota used up ({quota.used}/{quota.limit}). "
                "It resets tomorrow."
            )

        before = self.data.position.timestamp if self.data else None
        self._refreshing = True
        self.async_update_listeners()
        try:
            await self.client.async_get_position(self.vehicle, force_refresh=True)

            waited = 0
            settled = False
            while waited < REFRESH_TIMEOUT:
                await asyncio.sleep(REFRESH_POLL_INTERVAL)
                waited += REFRESH_POLL_INTERVAL
                position = await self.client.async_get_position(self.vehicle)
                if self.data:
                    self.async_set_updated_data(
                        VehicleData(
                            position=position,
                            services=self.data.services,
                            notifications=self.data.notifications,
                        )
                    )
                if position.timestamp != before:
                    _LOGGER.debug(
                        "Fresh fix for %s after %ss", self.vehicle.plate, waited
                    )
                    return
                if position.pending_request:
                    settled = False
                elif settled:
                    # Two consecutive settled reads with an unchanged
                    # timestamp: the box never answered.
                    break
                else:
                    settled = True

            _LOGGER.warning(
                "Position refresh for %s finished without a new fix. The box does "
                "not answer while the engine is off",
                self.vehicle.plate,
            )
        except UnipolSaiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UnipolSaiError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            self._refreshing = False
            self.async_update_listeners()


class UnipolSaiUniboxUsageCoordinator(DataUpdateCoordinator[UsageStats]):
    """Polls driving statistics. Free, and only changes daily."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: UnipolSaiClient,
        vehicle: Vehicle,
    ) -> None:
        """Set up the per-vehicle statistics coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {vehicle.plate} usage",
            update_interval=USAGE_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self.vehicle = vehicle

    async def _async_update_data(self) -> UsageStats:
        try:
            return await self.client.async_get_usage(self.vehicle)
        except UnipolSaiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except UnipolSaiError as err:
            raise UpdateFailed(str(err)) from err
