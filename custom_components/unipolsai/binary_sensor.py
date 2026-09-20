"""Binary sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
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
    """Set up binary sensors."""
    entities: list[BinarySensorEntity] = []
    for coordinator in entry.runtime_data.vehicles.values():
        entities.append(UnipolSaiUniboxRefreshPending(coordinator))
        entities.append(UnipolSaiUniboxCarFinder(coordinator))
    async_add_entities(entities)


class UnipolSaiUniboxRefreshPending(UnipolSaiUniboxEntity, BinarySensorEntity):
    """Whether the box is currently being asked for a fresh fix."""

    _attr_translation_key = "refresh_pending"
    _attr_icon = "mdi:crosshairs-question"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, "refresh_pending")

    @property
    def is_on(self) -> bool:
        """True while a refresh is outstanding."""
        # The API flag lags the request by a few seconds, so fold in the
        # button's own state to avoid a dead-looking UI right after a press.
        return bool(
            self.coordinator.data.position.pending_request
            or self.coordinator.refresh_in_progress
        )


class UnipolSaiUniboxCarFinder(UnipolSaiUniboxEntity, BinarySensorEntity):
    """Whether the Car Finder service is active on the contract."""

    _attr_translation_key = "car_finder_active"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, "car_finder_active")

    @property
    def is_on(self) -> bool:
        """True when positions can be read at all."""
        return self.car_finder_active
