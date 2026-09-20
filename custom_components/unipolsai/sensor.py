"""Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from pyunipolsai import ALERT_SERVICES, SERVICE_CAR_FINDER, UsageStats

from . import UnipolSaiUniboxConfigEntry
from .coordinator import (
    UnipolSaiUniboxCoordinator,
    UnipolSaiUniboxUsageCoordinator,
    VehicleData,
)
from .entity import UnipolSaiUniboxEntity, UnipolSaiUniboxUsageEntity


@dataclass(frozen=True, kw_only=True)
class UnipolSaiUniboxSensorDescription(SensorEntityDescription):
    """A sensor reading from the position and service poll."""

    value_fn: Callable[[VehicleData], Any]


SENSORS: tuple[UnipolSaiUniboxSensorDescription, ...] = (
    UnipolSaiUniboxSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.position.speed,
    ),
    UnipolSaiUniboxSensorDescription(
        key="heading",
        translation_key="heading",
        icon="mdi:compass",
        # The API returns a cardinal letter, not a bearing, so this stays a
        # text sensor. The degrees are on the tracker as an attribute.
        value_fn=lambda data: data.position.heading,
    ),
    UnipolSaiUniboxSensorDescription(
        key="last_fix",
        translation_key="last_fix",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.position.timestamp,
    ),
    UnipolSaiUniboxSensorDescription(
        key="refreshes_used",
        translation_key="refreshes_used",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.position.quota.used,
    ),
    UnipolSaiUniboxSensorDescription(
        key="refreshes_remaining",
        translation_key="refreshes_remaining",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.position.quota.remaining,
    ),
    UnipolSaiUniboxSensorDescription(
        key="car_finder_credits",
        translation_key="car_finder_credits",
        icon="mdi:ticket-confirmation",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            service.credits_available
            if (service := data.services.get(SERVICE_CAR_FINDER))
            else None
        ),
    ),
)


@dataclass(frozen=True, kw_only=True)
class UnipolSaiUniboxUsageDescription(SensorEntityDescription):
    """A sensor reading from the driving statistics."""

    value_fn: Callable[[UsageStats], Any]


def _distance(key: str, kind: str) -> UnipolSaiUniboxUsageDescription:
    return UnipolSaiUniboxUsageDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        # Cumulative since the contract started, and the API can restate it,
        # so TOTAL rather than TOTAL_INCREASING.
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda usage: usage.distance_km(kind),
    )


USAGE_SENSORS: tuple[UnipolSaiUniboxUsageDescription, ...] = (
    _distance("total_distance", "total"),
    _distance("city_distance", "city"),
    _distance("extra_urban_distance", "extraUrban"),
    _distance("highway_distance", "highway"),
    UnipolSaiUniboxUsageDescription(
        key="total_driving_time",
        translation_key="total_driving_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda usage: usage.time_h("total"),
    ),
    UnipolSaiUniboxUsageDescription(
        key="top_province",
        translation_key="top_province",
        icon="mdi:map-marker-radius",
        value_fn=lambda usage: usage.top_province,
    ),
    UnipolSaiUniboxUsageDescription(
        key="top_province_share",
        translation_key="top_province_share",
        icon="mdi:chart-pie",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda usage: usage.top_province_share,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiUniboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    data = entry.runtime_data
    entities: list[SensorEntity] = []

    for plate, coordinator in data.vehicles.items():
        entities.extend(
            UnipolSaiUniboxSensor(coordinator, description) for description in SENSORS
        )
        entities.append(UnipolSaiUniboxLastCrashSensor(coordinator))
        entities.append(UnipolSaiUniboxCrashCountSensor(coordinator))
        entities.extend(
            UnipolSaiUniboxLastAlertSensor(coordinator, service, event_type)
            for service, event_type in ALERT_SERVICES.items()
            if coordinator.data.service_active(service)
        )
        if usage := data.usage.get(plate):
            entities.extend(
                UnipolSaiUniboxUsageSensor(usage, description)
                for description in USAGE_SENSORS
            )

    async_add_entities(entities)


class UnipolSaiUniboxSensor(UnipolSaiUniboxEntity, SensorEntity):
    """A reading from the position and service poll."""

    entity_description: UnipolSaiUniboxSensorDescription

    def __init__(
        self,
        coordinator: UnipolSaiUniboxCoordinator,
        description: UnipolSaiUniboxSensorDescription,
    ) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Current value."""
        return self.entity_description.value_fn(self.coordinator.data)


class UnipolSaiUniboxUsageSensor(UnipolSaiUniboxUsageEntity, SensorEntity):
    """A reading from the driving statistics."""

    entity_description: UnipolSaiUniboxUsageDescription

    def __init__(
        self,
        coordinator: UnipolSaiUniboxUsageCoordinator,
        description: UnipolSaiUniboxUsageDescription,
    ) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Current value."""
        return self.entity_description.value_fn(self.coordinator.data)


class UnipolSaiUniboxLastAlertSensor(UnipolSaiUniboxEntity, SensorEntity):
    """When the most recent event for one alert service happened."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: UnipolSaiUniboxCoordinator,
        service: str,
        event_type: str,
    ) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, f"last_{service}")
        self._service = service
        self._attr_translation_key = f"last_{event_type}"

    @property
    def native_value(self) -> datetime | None:
        """Timestamp of the latest event."""
        latest = self.coordinator.data.latest(self._service)
        return latest.occurred_at if latest else None

    @property
    def extra_state_attributes(self) -> dict:
        """Where the event happened, which is not the current position."""
        latest = self.coordinator.data.latest(self._service)
        if latest is None:
            return {}
        return {
            "latitude": latest.latitude,
            "longitude": latest.longitude,
            "speed": latest.speed,
        }


class UnipolSaiUniboxLastCrashSensor(UnipolSaiUniboxEntity, SensorEntity):
    """When the box last reported an impact."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_crash"
    _attr_icon = "mdi:car-emergency"

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, "last_crash")

    @property
    def native_value(self) -> datetime | None:
        """Timestamp of the most recent impact."""
        crash = self.coordinator.data.latest_crash
        return crash.occurred_at if crash else None

    @property
    def extra_state_attributes(self) -> dict:
        """Where it happened and how hard, for the most recent one."""
        crash = self.coordinator.data.latest_crash
        if crash is None:
            return {}
        return {
            "crash_id": crash.id,
            "latitude": crash.latitude,
            "longitude": crash.longitude,
            "speed": crash.speed,
            "max_acceleration": crash.max_acceleration,
            "validated": crash.validated,
        }


class UnipolSaiUniboxCrashCountSensor(UnipolSaiUniboxEntity, SensorEntity):
    """How many impacts the box has on record."""

    _attr_translation_key = "crash_count"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: UnipolSaiUniboxCoordinator) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, "crash_count")

    @property
    def native_value(self) -> int:
        """Number of impacts on record."""
        return len(self.coordinator.data.crashes)

    @property
    def extra_state_attributes(self) -> dict:
        """Split out the ones that were graded as accidents."""
        crashes = self.coordinator.data.crashes
        return {"validated": sum(1 for c in crashes if c.validated)}
