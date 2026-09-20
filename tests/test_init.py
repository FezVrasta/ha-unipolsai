"""Setup, unload, and what happens when the account is unreachable."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyunipolsai import UnipolSaiAuthError, UnipolSaiError, Vehicle


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """A reachable account sets up, and unloading leaves nothing behind."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("error", "expected_state"),
    [
        (UnipolSaiError("gateway down"), ConfigEntryState.SETUP_RETRY),
        (UnipolSaiAuthError("password rejected"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_failures(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    config_entry: MockConfigEntry,
    error: Exception,
    expected_state: ConfigEntryState,
) -> None:
    """A transient failure retries; a credential failure asks for help.

    Getting these the wrong way round means either retrying a rejected
    password forever, or giving up on a gateway that was merely restarting.
    """
    mock_client.async_get_vehicles.side_effect = error
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is expected_state


async def test_account_without_a_box_retries(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """An account with no active box is not a permanent error.

    A contract can be activated later, so this retries rather than parking
    the entry in a state the user has to notice and fix.
    """
    mock_client.async_get_vehicles.return_value = []
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_vehicle_without_device_id_still_works(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """A box with no reported id falls back to the plate for identity."""
    mock_client.async_get_vehicles.return_value = [
        Vehicle(plate="ZZ999ZZ", contract_open=True, terminal_active=True)
    ]
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("device_tracker.zz999zz") is not None
