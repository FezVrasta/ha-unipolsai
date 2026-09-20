"""Shared entity base for the UnipolSai Unibox integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnipolSaiCoordinator, UnipolSaiUsageCoordinator


def build_device_info(plate: str, contract: dict) -> DeviceInfo:
    """One HA device per vehicle."""
    vehicle = contract.get("veicolo") or {}
    device = contract.get("dispositivoTelematico") or {}
    make = vehicle.get("marca") or ""
    model = vehicle.get("modello") or ""
    return DeviceInfo(
        identifiers={(DOMAIN, plate)},
        name=f"{make.title()} {plate}".strip(),
        manufacturer=make.title() or "UnipolSai",
        model=model.title() or "Unibox",
        serial_number=device.get("idDispositivo"),
    )


class UnipolSaiEntity(CoordinatorEntity[UnipolSaiCoordinator]):
    """Base for entities backed by the position/VAS coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UnipolSaiCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.plate}_{key}"
        self._attr_device_info = build_device_info(
            coordinator.plate, coordinator.vehicle
        )

    @property
    def position(self) -> dict:
        return (self.coordinator.data or {}).get("position") or {}

    @property
    def vas(self) -> dict:
        return (self.coordinator.data or {}).get("vas") or {}

    @property
    def car_finder_active(self) -> bool:
        return bool((self.vas.get("carFinder") or {}).get("isServiceActivated"))


class UnipolSaiUsageEntity(CoordinatorEntity[UnipolSaiUsageCoordinator]):
    """Base for entities backed by the driving-statistics coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnipolSaiUsageCoordinator,
        key: str,
        contract: dict,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.plate}_{key}"
        self._attr_device_info = build_device_info(coordinator.plate, contract)
