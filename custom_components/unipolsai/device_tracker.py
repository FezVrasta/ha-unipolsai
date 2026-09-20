"""Vehicle location."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UnipolSaiUniboxConfigEntry
from .coordinator import UnipolSaiUniboxCoordinator
from .entity import UnipolSaiUniboxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiUniboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one tracker per vehicle."""
    async_add_entities(
        UnipolSaiUniboxTracker(coordinator)
        for coordinator in entry.runtime_data.vehicles.values()
    )


class UnipolSaiUniboxTracker(UnipolSaiUniboxEntity, TrackerEntity):
    """Where the box last reported the vehicle."""

    _attr_name = None
    _attr_icon = "mdi:car"

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator) -> None:
        """Set up the tracker."""
        super().__init__(coordinator, "tracker")

    @property
    def source_type(self) -> SourceType:
        """Report GPS, which is what the box uses."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Latitude of the last reported position."""
        return self.coordinator.data.position.latitude

    @property
    def longitude(self) -> float | None:
        """Longitude of the last reported position."""
        return self.coordinator.data.position.longitude

    # `location_accuracy` is deliberately left at its default. The API's
    # `accuracy` is a small quality grade, not a radius in metres, so
    # reporting it would tell Home Assistant the fix is good to one metre and
    # make every zone check wrong.

    @property
    def available(self) -> bool:
        """Unavailable when the position service is switched off."""
        return super().available and self.car_finder_active

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the readings that have no entity of their own."""
        position = self.coordinator.data.position
        return {
            "heading": position.heading,
            "heading_degrees": position.heading_degrees,
            "quality": position.quality,
            "refresh_pending": position.pending_request,
            "refreshes_used_today": position.quota.used,
            "refreshes_per_day": position.quota.limit,
        }
