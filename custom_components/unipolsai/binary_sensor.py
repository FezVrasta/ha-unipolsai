"""Binary sensors for the UnipolSai Unibox."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UnipolSaiConfigEntry
from .entity import UnipolSaiEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    entities: list[BinarySensorEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        entities.append(UnipolSaiRefreshPending(coordinator))
        entities.append(UnipolSaiCarFinderActive(coordinator))
    async_add_entities(entities)


class UnipolSaiRefreshPending(UnipolSaiEntity, BinarySensorEntity):
    """Whether the box is currently being asked for a fresh fix."""

    _attr_translation_key = "refresh_pending"
    _attr_icon = "mdi:crosshairs-question"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "refresh_pending")

    @property
    def is_on(self) -> bool:
        # The API flag lags the request by a few seconds, so OR in the button's
        # own state to avoid a dead-looking UI right after a press.
        return bool(
            self.position.get("pendingRequest") or self.coordinator.refresh_in_progress
        )


class UnipolSaiCarFinderActive(UnipolSaiEntity, BinarySensorEntity):
    """Whether the Car Finder service is active on the contract."""

    _attr_translation_key = "car_finder_active"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "car_finder_active")

    @property
    def is_on(self) -> bool:
        return self.car_finder_active
