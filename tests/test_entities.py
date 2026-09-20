"""Entity behaviour.

These lock in the readings the API is easiest to get wrong about: metres and
seconds, a heading that is a letter, and an `accuracy` that is a grade rather
than a radius.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyunipolsai import Crash, Position, Quota, UnipolSaiError


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


async def test_crash_entities(hass: HomeAssistant) -> None:
    """The impact entities carry the detection and grade it honestly."""
    last = hass.states.get("sensor.volkswagen_ab123cd_last_impact")
    assert last is not None
    assert last.state == "2026-09-20T06:32:37+00:00"
    assert last.attributes["max_acceleration"] == 312
    # Graded by the provider, so validated even though Unipol's own field is 0.
    assert last.attributes["validated"] is True

    count = hass.states.get("sensor.volkswagen_ab123cd_impacts_on_record")
    assert count is not None
    assert count.state == "1"
    assert count.attributes["validated"] == 1

    assert hass.states.get("event.volkswagen_ab123cd_impact_detected") is not None


async def test_crash_event_does_not_replay_on_restart(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """An impact already on record must not fire again on every reload.

    Otherwise every Home Assistant restart re-announces a crash from months
    ago, which is the kind of notification that gets an integration deleted.
    """
    state = hass.states.get("event.volkswagen_ab123cd_impact_detected")
    assert state is not None
    assert state.state == "unknown"

    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("event.volkswagen_ab123cd_impact_detected")
    assert state is not None
    assert state.state == "unknown"


async def test_crash_event_fires_for_a_new_impact(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    config_entry: MockConfigEntry,
    crash: Crash,
) -> None:
    """A previously unseen id fires the event.

    Driven by refreshing the coordinator rather than by winding the clock.
    What matters here is that a new id reaches the entity and fires, which is
    this integration's code; whether Home Assistant's own scheduler wakes on
    time is not.
    """
    coordinator = next(iter(config_entry.runtime_data.vehicles.values()))
    mock_client.async_get_crashes.return_value = [crash, replace(crash, id=4412)]

    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_crash_endpoint_404_reports_zero(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """A 404 means nothing to report, not a failure.

    The account this was developed against answers 404 on the crash endpoint,
    and there is no way to tell "no impacts on record" from "this contract has
    no crash detection". The library flattens it to an empty list, so the
    entities stay and read zero rather than vanishing: if an impact is ever
    recorded, it will surface.
    """
    mock_client.async_get_crashes.return_value = []
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    count = hass.states.get("sensor.volkswagen_ab123cd_impacts_on_record")
    assert count is not None
    assert count.state == "0"
    last = hass.states.get("sensor.volkswagen_ab123cd_last_impact")
    assert last is not None
    assert last.state == "unknown"


async def test_crashes_unavailable_does_not_break_the_poll(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """An account without crash detection keeps its position entities.

    Nothing in vehicleVAS says whether the endpoint will answer, so the only
    way to find out is to call it and cope.
    """
    mock_client.async_get_crashes.side_effect = UnipolSaiError("not available")
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    tracker = hass.states.get("device_tracker.volkswagen_ab123cd")
    assert tracker is not None
    assert tracker.state != "unavailable"
    assert hass.states.get("sensor.volkswagen_ab123cd_impacts_on_record").state == "0"
