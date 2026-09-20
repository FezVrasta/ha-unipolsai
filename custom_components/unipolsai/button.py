"""Forced position refresh.

A button rather than automatic behaviour: there are only five forced
refreshes a day, shared with anything else touching the account, the phone
app included.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up the refresh button."""
    async_add_entities(
        UnipolSaiUniboxRefreshButton(coordinator)
        for coordinator in entry.runtime_data.vehicles.values()
    )


class UnipolSaiUniboxRefreshButton(UnipolSaiUniboxEntity, ButtonEntity):
    """Ask the box to report a fresh position."""

    _attr_translation_key = "force_refresh"
    _attr_icon = "mdi:crosshairs-gps"

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator) -> None:
        """Set up the button."""
        super().__init__(coordinator, "force_refresh")

    @property
    def available(self) -> bool:
        """Unavailable while one is running, or once the budget is spent."""
        if not super().available or not self.car_finder_active:
            return False
        if self.coordinator.refresh_in_progress:
            return False
        return not self.coordinator.data.position.quota.exhausted

    async def async_press(self) -> None:
        """Fire the refresh and wait out the cycle."""
        await self.coordinator.async_force_refresh()
