"""Device tracker for the UnipolSai Unibox."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UnipolSaiConfigEntry
from .const import HEADING_DEGREES
from .entity import UnipolSaiEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one tracker per vehicle."""
    async_add_entities(
        UnipolSaiTracker(coordinator)
        for coordinator in entry.runtime_data.coordinators.values()
    )


class UnipolSaiTracker(UnipolSaiEntity, TrackerEntity):
    """The vehicle's last known position."""

    _attr_name = None
    _attr_icon = "mdi:car"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "tracker")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self.position.get("lat")

    @property
    def longitude(self) -> float | None:
        return self.position.get("lon")

    # No location_accuracy on purpose. The API's `accuracy` is a small integer
    # grade, not a radius in metres, and reporting it would tell HA the fix is
    # good to 1 metre. See docs/FINDINGS.md.

    @property
    def available(self) -> bool:
        return super().available and self.car_finder_active

    @property
    def extra_state_attributes(self) -> dict:
        position = self.position
        heading = position.get("heading")
        quota = position.get("dailyFruitions") or {}
        return {
            "speed": position.get("speed"),
            "heading": heading,
            "heading_degrees": HEADING_DEGREES.get(heading),
            "quality": position.get("accuracy"),
            "refresh_pending": position.get("pendingRequest"),
            "refreshes_used_today": quota.get("current"),
            "refreshes_per_day": quota.get("max"),
        }
