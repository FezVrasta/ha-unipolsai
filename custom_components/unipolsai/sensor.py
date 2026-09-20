"""Sensors for the UnipolSai Unibox."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UnipolSaiConfigEntry
from .entity import UnipolSaiEntity, UnipolSaiUsageEntity


def _epoch_ms(value: Any) -> datetime | None:
    """The API sends epoch milliseconds, despite declaring the field String."""
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


@dataclass(frozen=True, kw_only=True)
class PositionSensorDescription(SensorEntityDescription):
    """A sensor reading from the position/VAS payload."""

    value_fn: Callable[[dict, dict], Any]


POSITION_SENSORS: tuple[PositionSensorDescription, ...] = (
    PositionSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda pos, vas: pos.get("speed"),
    ),
    PositionSensorDescription(
        key="heading",
        translation_key="heading",
        icon="mdi:compass",
        # A cardinal letter, not degrees, so this stays a plain text sensor.
        value_fn=lambda pos, vas: pos.get("heading"),
    ),
    PositionSensorDescription(
        key="last_fix",
        translation_key="last_fix",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda pos, vas: _epoch_ms(pos.get("date")),
    ),
    PositionSensorDescription(
        key="refreshes_used",
        translation_key="refreshes_used",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda pos, vas: (pos.get("dailyFruitions") or {}).get("current"),
    ),
    PositionSensorDescription(
        key="refreshes_remaining",
        translation_key="refreshes_remaining",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda pos, vas: (
            None
            if not (q := pos.get("dailyFruitions"))
            or q.get("max") is None
            or q.get("current") is None
            else max(0, q["max"] - q["current"])
        ),
    ),
    PositionSensorDescription(
        key="car_finder_credits",
        translation_key="car_finder_credits",
        icon="mdi:ticket-confirmation",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda pos, vas: (vas.get("carFinder") or {}).get(
            "serviceAvailableCredits"
        ),
    ),
)


@dataclass(frozen=True, kw_only=True)
class UsageSensorDescription(SensorEntityDescription):
    """A sensor reading from the vehicleUsages payload."""

    value_fn: Callable[[dict], Any]


def _km(field: str) -> Callable[[dict], Any]:
    """vehicleUsages distances are METRES. Off by 1000x if you assume km."""
    return lambda d: None if d.get(field) is None else round(d[field] / 1000, 1)


def _hours(field: str) -> Callable[[dict], Any]:
    """vehicleUsages times are SECONDS."""
    return lambda d: None if d.get(field) is None else round(d[field] / 3600, 2)


def _distance(key: str, field: str) -> UsageSensorDescription:
    return UsageSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        # Cumulative since the contract started, and it can be restated,
        # so TOTAL rather than TOTAL_INCREASING.
        state_class=SensorStateClass.TOTAL,
        value_fn=_km(field),
    )


USAGE_SENSORS: tuple[UsageSensorDescription, ...] = (
    _distance("total_distance", "totalDistance"),
    _distance("city_distance", "cityDrivingDistance"),
    _distance("extra_urban_distance", "extraUrbanDrivingDistance"),
    _distance("highway_distance", "highwayDrivingDistance"),
    UsageSensorDescription(
        key="total_driving_time",
        translation_key="total_driving_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL,
        value_fn=_hours("totalDrivingTime"),
    ),
    UsageSensorDescription(
        key="top_province",
        translation_key="top_province",
        icon="mdi:map-marker-radius",
        value_fn=lambda d: d.get("higherMileageProvinceFullName"),
    ),
    UsageSensorDescription(
        key="top_province_share",
        translation_key="top_province_share",
        icon="mdi:chart-pie",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("higherMileageProvinceDrivingPerc"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UnipolSaiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    data = entry.runtime_data
    entities: list[SensorEntity] = []

    for plate, coordinator in data.coordinators.items():
        entities.extend(
            UnipolSaiPositionSensor(coordinator, description)
            for description in POSITION_SENSORS
        )
        if usage := data.usage.get(plate):
            entities.extend(
                UnipolSaiUsageSensor(usage, description, coordinator.vehicle)
                for description in USAGE_SENSORS
            )

    async_add_entities(entities)


class UnipolSaiPositionSensor(UnipolSaiEntity, SensorEntity):
    """A sensor derived from lastPosition or vehicleVAS."""

    entity_description: PositionSensorDescription

    def __init__(self, coordinator, description: PositionSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.position, self.vas)


class UnipolSaiUsageSensor(UnipolSaiUsageEntity, SensorEntity):
    """A sensor derived from vehicleUsages."""

    entity_description: UsageSensorDescription

    def __init__(
        self, coordinator, description: UsageSensorDescription, contract: dict
    ) -> None:
        super().__init__(coordinator, description.key, contract)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})
