"""Shared entity bases."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from pyunipolsai import SERVICE_CAR_FINDER, Vehicle

from .const import DOMAIN
from .coordinator import UnipolSaiUniboxCoordinator, UnipolSaiUniboxUsageCoordinator


def device_identity(vehicle: Vehicle) -> str:
    """Return the stable identifier for one vehicle's box.

    The box's own id, not the plate: a plate can be reassigned and the box can
    be moved to another car, and either would orphan every entity's history if
    it were part of the unique ID.
    """
    return vehicle.device.device_id or vehicle.plate


def build_device_info(vehicle: Vehicle) -> DeviceInfo:
    """One Home Assistant device per vehicle."""
    make = (vehicle.make or "").title()
    return DeviceInfo(
        identifiers={(DOMAIN, device_identity(vehicle))},
        name=f"{make} {vehicle.plate}".strip(),
        manufacturer=make or "UnipolSai",
        model=(vehicle.model or "Unibox").title(),
        serial_number=vehicle.device.device_id,
    )


class UnipolSaiUniboxEntity(CoordinatorEntity[UnipolSaiUniboxCoordinator]):
    """Base for entities backed by the position and service poll."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator, key: str) -> None:
        """Bind to the coordinator and take a permanent ID from the box."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_identity(coordinator.vehicle)}_{key}"
        self._attr_device_info = build_device_info(coordinator.vehicle)

    @property
    def car_finder_active(self) -> bool:
        """Whether the position service is switched on for this contract."""
        return bool(self.coordinator.data) and self.coordinator.data.service_active(
            SERVICE_CAR_FINDER
        )


class UnipolSaiUniboxUsageEntity(CoordinatorEntity[UnipolSaiUniboxUsageCoordinator]):
    """Base for entities backed by the driving-statistics poll."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UnipolSaiUniboxUsageCoordinator, key: str) -> None:
        """Bind to the statistics coordinator."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_identity(coordinator.vehicle)}_{key}"
        self._attr_device_info = build_device_info(coordinator.vehicle)
