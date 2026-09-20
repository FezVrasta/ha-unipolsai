"""Event entities for the Unibox alert services.

`lastNotifications` returns only the most recent event per service, so this
works by watching the notification `id` and firing when it changes. The app
receives these as push; here they arrive on the coordinator's poll, so expect
them a few minutes late.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UnipolSaiConfigEntry
from .const import ALERT_SERVICES
from .coordinator import UnipolSaiCoordinator
from .entity import UnipolSaiEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an event entity per activated alert service."""
    entities: list[EventEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        vas = (coordinator.data or {}).get("vas") or {}
        for service, event_type in ALERT_SERVICES.items():
            if (vas.get(service) or {}).get("isServiceActivated"):
                entities.append(
                    UnipolSaiAlertEvent(coordinator, service, event_type)
                )
    async_add_entities(entities)


class UnipolSaiAlertEvent(UnipolSaiEntity, EventEntity):
    """Fires when a new notification appears for one alert service."""

    def __init__(
        self, coordinator: UnipolSaiCoordinator, service: str, event_type: str
    ) -> None:
        super().__init__(coordinator, f"event_{service}")
        self._service = service
        self._attr_translation_key = event_type
        self._attr_event_types = [event_type]
        self._event_type = event_type
        self._last_id: str | None = None

    @property
    def _latest(self) -> dict | None:
        notifications = (
            (self.coordinator.data or {}).get("notifications") or {}
        ).get(self._service) or []
        return notifications[0] if notifications else None

    async def async_added_to_hass(self) -> None:
        """Seed the last-seen id so a restart doesn't replay a stale event."""
        await super().async_added_to_hass()
        if latest := self._latest:
            self._last_id = latest.get("id")

    @callback
    def _handle_coordinator_update(self) -> None:
        latest = self._latest
        if latest and (event_id := latest.get("id")) and event_id != self._last_id:
            self._last_id = event_id
            event_date = latest.get("eventDate")
            self._trigger_event(
                self._event_type,
                {
                    "event_id": event_id,
                    # epoch millis, like every other date in this API
                    "occurred_at": (
                        datetime.fromtimestamp(event_date / 1000, tz=UTC).isoformat()
                        if isinstance(event_date, (int, float))
                        else None
                    ),
                    "latitude": latest.get("latitude"),
                    "longitude": latest.get("longitude"),
                    "speed": latest.get("speed"),
                    "speed_limit": latest.get("speedLimitValue") or None,
                },
            )
            _LOGGER.debug(
                "%s event for %s at %s", self._event_type, self.coordinator.plate,
                event_date,
            )
        super()._handle_coordinator_update()
