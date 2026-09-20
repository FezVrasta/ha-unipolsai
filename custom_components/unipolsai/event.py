"""Alert events.

`lastNotifications` returns only the most recent event per service, so this
watches the notification id and fires when it changes. The app receives these
as push; here they arrive on the coordinator's poll, so expect them a few
minutes late.
"""

from __future__ import annotations

import logging

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from pyunipolsai import ALERT_SERVICES, Notification

from . import UnipolSaiUniboxConfigEntry
from .coordinator import UnipolSaiUniboxCoordinator
from .entity import UnipolSaiUniboxEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiUniboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up an event entity per activated alert service, plus crashes."""
    entities: list[EventEntity] = [
        UnipolSaiUniboxAlertEvent(coordinator, service, event_type)
        for coordinator in entry.runtime_data.vehicles.values()
        for service, event_type in ALERT_SERVICES.items()
        if coordinator.data.service_active(service)
    ]
    # Crash detection is not one of the credit-gated services, so there is no
    # flag to check: it is created whenever the endpoint answered at all.
    entities.extend(
        UnipolSaiUniboxCrashEvent(coordinator)
        for coordinator in entry.runtime_data.vehicles.values()
    )
    async_add_entities(entities)


class UnipolSaiUniboxAlertEvent(UnipolSaiUniboxEntity, EventEntity):
    """Fires when a new notification appears for one alert service."""

    def __init__(
        self,
        coordinator: UnipolSaiUniboxCoordinator,
        service: str,
        event_type: str,
    ) -> None:
        """Set up the event entity."""
        super().__init__(coordinator, f"event_{service}")
        self._service = service
        self._event_type = event_type
        self._attr_translation_key = event_type
        self._attr_event_types = [event_type]
        self._last_id: str | None = None

    @property
    def _latest(self) -> Notification | None:
        return self.coordinator.data.latest(self._service)

    async def async_added_to_hass(self) -> None:
        """Seed the last-seen id so a restart does not replay a stale event."""
        await super().async_added_to_hass()
        if latest := self._latest:
            self._last_id = latest.id

    @callback
    def _handle_coordinator_update(self) -> None:
        latest = self._latest
        if latest is not None and latest.id != self._last_id:
            self._last_id = latest.id
            self._trigger_event(
                self._event_type,
                {
                    "event_id": latest.id,
                    "occurred_at": (
                        latest.occurred_at.isoformat() if latest.occurred_at else None
                    ),
                    # The event's own coordinates, independent of where the
                    # vehicle is now.
                    "latitude": latest.latitude,
                    "longitude": latest.longitude,
                    "speed": latest.speed,
                    "speed_limit": latest.speed_limit,
                },
            )
            _LOGGER.debug(
                "%s for %s at %s",
                self._event_type,
                self.coordinator.vehicle.plate,
                latest.occurred_at,
            )
        super()._handle_coordinator_update()


class UnipolSaiUniboxCrashEvent(UnipolSaiUniboxEntity, EventEntity):
    """Fires when the box reports an impact it has not reported before.

    A detection is not a confirmed accident. `validated` says whether either
    Unipol or the telematics provider has graded it as one, and it is in the
    event data rather than gating the event, because a detection the provider
    later dismisses is still something a person would want to know happened.
    """

    _attr_translation_key = "crash"
    _attr_event_types = ["crash"]
    _attr_icon = "mdi:car-emergency"

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator) -> None:
        """Set up the event entity."""
        super().__init__(coordinator, "event_crash")
        self._seen: set[int] = set()

    async def async_added_to_hass(self) -> None:
        """Seed the seen ids so a restart does not replay old impacts."""
        await super().async_added_to_hass()
        self._seen = {c.id for c in self.coordinator.data.crashes}

    @callback
    def _handle_coordinator_update(self) -> None:
        for crash in self.coordinator.data.crashes:
            if crash.id in self._seen:
                continue
            self._seen.add(crash.id)
            self._trigger_event(
                "crash",
                {
                    "crash_id": crash.id,
                    "occurred_at": (
                        crash.occurred_at.isoformat() if crash.occurred_at else None
                    ),
                    "latitude": crash.latitude,
                    "longitude": crash.longitude,
                    "speed": crash.speed,
                    "max_acceleration": crash.max_acceleration,
                    "validated": crash.validated,
                },
            )
            _LOGGER.warning(
                "Impact reported for %s at %s, validated=%s",
                self.coordinator.vehicle.plate,
                crash.occurred_at,
                crash.validated,
            )
        super()._handle_coordinator_update()
