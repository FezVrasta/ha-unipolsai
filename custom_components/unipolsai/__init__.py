"""The UnipolSai Unibox integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import UnipolSaiApi, UnipolSaiAuthError, UnipolSaiError
from .helpers import gateway_credentials
from .coordinator import UnipolSaiCoordinator, UnipolSaiUsageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
    Platform.SENSOR,
]


@dataclass
class UnipolSaiData:
    """Runtime data for a config entry."""

    api: UnipolSaiApi
    coordinators: dict[str, UnipolSaiCoordinator] = field(default_factory=dict)
    usage: dict[str, UnipolSaiUsageCoordinator] = field(default_factory=dict)


type UnipolSaiConfigEntry = ConfigEntry[UnipolSaiData]


async def async_setup_entry(hass: HomeAssistant, entry: UnipolSaiConfigEntry) -> bool:
    """Set up from a config entry."""
    # A dedicated session: the F5 cookies set at login must persist across
    # every call and must not leak into HA's shared session.
    session = async_create_clientsession(hass)
    api = UnipolSaiApi(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        *gateway_credentials(entry),
    )

    try:
        await api.login()
        contracts = await api.telematic_contracts()
    except UnipolSaiAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except UnipolSaiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    data = UnipolSaiData(api=api)

    for contract in contracts:
        vehicle = contract.get("veicolo") or {}
        plate = vehicle.get("targa")
        if not plate:
            continue
        if contract.get("statoTerminale") != "active":
            _LOGGER.info(
                "Skipping %s: terminal state is %s",
                plate,
                contract.get("statoTerminale"),
            )
            continue

        coordinator = UnipolSaiCoordinator(hass, entry, api, plate, contract)
        await coordinator.async_config_entry_first_refresh()
        data.coordinators[plate] = coordinator

        usage = UnipolSaiUsageCoordinator(hass, entry, api, plate)
        await usage.async_config_entry_first_refresh()
        data.usage[plate] = usage

    if not data.coordinators:
        raise ConfigEntryNotReady(
            "No vehicle with an active Unibox was found on this account"
        )

    entry.runtime_data = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: UnipolSaiConfigEntry) -> None:
    """Reload when the gateway credentials are overridden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: UnipolSaiConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
