"""Shared fixtures.

Home Assistant's own test fixtures come from `pytest-homeassistant-custom-component`,
which registers itself as a pytest plugin — so the suite needs only the installed
package, not a checkout of Home Assistant core. That package pins the Home Assistant
version the suite runs against; bump it in `requirements-test.txt` to test against a
newer one.

The protocol client lives in `pyunipolsai` and has its own tests. Here it is always
mocked, so a change to the wire format surfaces in the library's suite rather than
breaking every integration test at once.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unipolsai.const import DOMAIN
from pyunipolsai import (
    Notification,
    Position,
    Quota,
    Service,
    TelematicDevice,
    UsageStats,
    Vehicle,
)

USERNAME = "someone@example.com"
DEVICE_ID = "220200000000000000"


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load this integration in every test."""


@pytest.fixture
def vehicle() -> Vehicle:
    """Return a vehicle with an active box."""
    return Vehicle(
        plate="AB123CD",
        make="VOLKSWAGEN",
        model="T-ROC",
        contract_id="27778190",
        contract_open=True,
        terminal_active=True,
        device=TelematicDevice(
            device_id=DEVICE_ID, imei="000000000000000", device_type="F"
        ),
    )


@pytest.fixture
def position() -> Position:
    """Return a settled position with the daily budget untouched."""
    return Position(
        latitude=45.4642,
        longitude=9.19,
        speed=0,
        heading="N",
        quality=1,
        timestamp=datetime(2026, 9, 20, 7, 28, 31, tzinfo=UTC),
        pending_request=False,
        quota=Quota(used=0, limit=5),
    )


@pytest.fixture
def services() -> dict[str, Service]:
    """Car Finder, engine alerts and statistics switched on."""
    return {
        "carFinder": Service(
            name="carFinder",
            enabled=True,
            activated=True,
            requires_credits=True,
            credits_available=9,
            credits_used=1,
        ),
        "engineOn": Service(
            name="engineOn",
            enabled=True,
            activated=True,
            requires_credits=True,
            credits_available=9,
            credits_used=1,
        ),
        "speedLimit": Service(name="speedLimit", enabled=True, activated=False),
        "rangeStatistics": Service(
            name="rangeStatistics", enabled=True, activated=True
        ),
    }


@pytest.fixture
def notification() -> Notification:
    """One engine-start event."""
    return Notification(
        id="68b1e071-0000-0000-0000-000000000000",
        occurred_at=datetime(2026, 9, 20, 6, 32, 37, tzinfo=UTC),
        latitude=45.48,
        longitude=9.2,
        speed=0,
        plate="IT-AB123CD",
        provider="Alfa",
    )


@pytest.fixture
def usage() -> UsageStats:
    """Driving statistics over a quarter."""
    return UsageStats.from_api(
        {
            "fromDate": 1781913600000,
            "toDate": 1789689600000,
            "totalDistance": 5431730,
            "totalDrivingTime": 420215,
            "cityDrivingDistance": 1378360,
            "highwayDrivingDistance": 1888260,
            "higherMileageProvinceFullName": "Province",
            "higherMileageProvinceDrivingPerc": 41.58,
            "totalDaysUsedForAnalysis": 91,
        }
    )


@pytest.fixture
def mock_client(
    vehicle: Vehicle,
    position: Position,
    services: dict[str, Service],
    notification: Notification,
    usage: UsageStats,
) -> Generator[AsyncMock]:
    """Patch the client everywhere the integration constructs one."""
    with (
        patch(
            "custom_components.unipolsai.UnipolSaiClient", autospec=True
        ) as client_class,
        patch(
            "custom_components.unipolsai.config_flow.UnipolSaiClient",
            new=client_class,
        ),
    ):
        client = client_class.return_value
        client.async_get_vehicles = AsyncMock(return_value=[vehicle])
        client.async_get_position = AsyncMock(return_value=position)
        client.async_get_services = AsyncMock(return_value=services)
        client.async_get_notifications = AsyncMock(return_value=[notification])
        client.async_get_usage = AsyncMock(return_value=usage)
        client.async_close = AsyncMock()
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a configured entry, not yet added to Home Assistant."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=USERNAME,
        unique_id=USERNAME,
        data={CONF_USERNAME: USERNAME, CONF_PASSWORD: "hunter2"},
    )
