"""Entity behaviour.

These lock in the readings the API is easiest to get wrong about: metres and
seconds, a heading that is a letter, and an `accuracy` that is a grade rather
than a radius.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyunipolsai import Position, Quota


@pytest.fixture(autouse=True)
async def _setup(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Load the integration for every test in this module."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_tracker_reports_position(hass: HomeAssistant) -> None:
    """The tracker carries the coordinates and the extras."""
    state = hass.states.get("device_tracker.volkswagen_ab123cd")
    assert state is not None
    assert state.attributes["latitude"] == 45.4642
    assert state.attributes["longitude"] == 9.19
    assert state.attributes["heading"] == "N"
    assert state.attributes["heading_degrees"] == 0


async def test_tracker_reports_no_gps_accuracy(hass: HomeAssistant) -> None:
    """`accuracy` is a quality grade, not metres.

    Reporting it as `gps_accuracy` would claim a one-metre fix and make every
    zone check wrong, so the tracker leaves it unset and exposes the raw
    grade as `quality` instead.
    """
    state = hass.states.get("device_tracker.volkswagen_ab123cd")
    assert state is not None
    assert state.attributes.get("gps_accuracy") in (None, 0)
    assert state.attributes["quality"] == 1


async def test_quota_sensors(hass: HomeAssistant) -> None:
    """Both halves of the daily forced-refresh budget are exposed."""
    assert (
        hass.states.get("sensor.volkswagen_ab123cd_refreshes_used_today").state == "0"
    )
    assert (
        hass.states.get("sensor.volkswagen_ab123cd_refreshes_remaining_today").state
        == "5"
    )


async def test_usage_sensors_convert_units(hass: HomeAssistant) -> None:
    """The API sends metres and seconds; the sensors publish km and hours."""
    assert hass.states.get("sensor.volkswagen_ab123cd_total_distance").state == "5431.7"
    assert (
        hass.states.get("sensor.volkswagen_ab123cd_total_driving_time").state
        == "116.73"
    )


async def test_alert_entities_follow_activated_services(hass: HomeAssistant) -> None:
    """EngineOn is on, speedLimit is not, so only one pair exists."""
    assert hass.states.get("event.volkswagen_ab123cd_engine_started") is not None
    assert hass.states.get("sensor.volkswagen_ab123cd_last_engine_start") is not None
    assert hass.states.get("event.volkswagen_ab123cd_speed_limit_exceeded") is None


async def test_locate_button_refuses_when_quota_is_spent(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """The button goes unavailable rather than wasting a call that would fail."""
    mock_client.async_get_position.return_value = Position(
        latitude=45.4642, longitude=9.19, quota=Quota(used=5, limit=5)
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("button.volkswagen_ab123cd_locate_now")
    assert state is not None
    assert state.state == "unavailable"


async def test_locate_button_reports_an_exhausted_quota(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Calling it anyway explains why, rather than failing silently.

    And it must not spend the call finding out: the check happens before any
    request, so a user hammering the button past the limit costs nothing.
    """
    coordinator = next(iter(config_entry.runtime_data.vehicles.values()))
    coordinator.data.position = Position(quota=Quota(used=5, limit=5))
    calls_before = mock_client.async_get_position.await_count

    with pytest.raises(HomeAssistantError, match="quota"):
        await coordinator.async_force_refresh()

    assert mock_client.async_get_position.await_count == calls_before
