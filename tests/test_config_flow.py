"""Config, reauth and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unipolsai.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_TENANT,
    DOMAIN,
)
from pyunipolsai import UnipolSaiAuthError, UnipolSaiError

CREDENTIALS = {CONF_USERNAME: "someone@example.com", CONF_PASSWORD: "hunter2"}


async def test_user_flow(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """The happy path needs only a username and a password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CREDENTIALS
    # The gateway credentials are defaults, so nothing is persisted for them.
    assert result["options"] == {}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UnipolSaiAuthError("nope"), "invalid_auth"),
        (UnipolSaiError("down"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, mock_client: AsyncMock, error: Exception, expected: str
) -> None:
    """Every failure returns to the form, and the form still works after."""
    mock_client.async_get_vehicles.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    mock_client.async_get_vehicles.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_account_without_a_box_is_rejected(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Setting up an account with nothing to track would create no entities."""
    mock_client.async_get_vehicles.return_value = []
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["errors"] == {"base": "no_vehicles"}


async def test_single_entry_per_account(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """The same account twice would duplicate every entity."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """A new password is validated and saved in place."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "new-password"


async def test_reconfigure_rejects_a_different_account(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Repointing an entry at another account would merge two histories."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "someone.else@example.com", CONF_PASSWORD: "x"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


async def test_options_flow_overrides_gateway_credentials(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Rotated gateway credentials can be fixed without a release."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: "new-id",
            CONF_CLIENT_SECRET: "new-secret",
            CONF_TENANT: "new-tenant",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_CLIENT_ID] == "new-id"
