"""Force a position refresh.

Deliberately a button and not automatic behaviour: there are only five forced
refreshes a day, shared with whatever else touches the account, the phone app
included.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UnipolSaiConfigEntry
from .entity import UnipolSaiEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the refresh button."""
    async_add_entities(
        UnipolSaiRefreshButton(coordinator)
        for coordinator in entry.runtime_data.coordinators.values()
    )


class UnipolSaiRefreshButton(UnipolSaiEntity, ButtonEntity):
    """Ask the box to report a fresh position."""

    _attr_translation_key = "force_refresh"
    _attr_icon = "mdi:crosshairs-gps"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "force_refresh")

    @property
    def available(self) -> bool:
        if not super().available or not self.car_finder_active:
            return False
        if self.coordinator.refresh_in_progress:
            return False
        quota = self.position.get("dailyFruitions") or {}
        current, maximum = quota.get("current"), quota.get("max")
        if current is not None and maximum is not None:
            return current < maximum
        return True

    async def async_press(self) -> None:
        """Fire the refresh and wait out the ~5 minute cycle."""
        await self.coordinator.async_force_refresh()
