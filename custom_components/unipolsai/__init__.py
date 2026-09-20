"""The UnipolSai Unibox."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from pyunipolsai import UnipolSaiAuthError, UnipolSaiClient, UnipolSaiError

from .const import PLATFORMS
from .coordinator import UnipolSaiUniboxCoordinator, UnipolSaiUniboxUsageCoordinator
from .helpers import gateway_credentials

_LOGGER = logging.getLogger(__name__)


@dataclass
class UnipolSaiUniboxData:
    """Runtime data: one pair of coordinators per vehicle on the account."""

    client: UnipolSaiClient
    vehicles: dict[str, UnipolSaiUniboxCoordinator] = field(default_factory=dict)
    usage: dict[str, UnipolSaiUniboxUsageCoordinator] = field(default_factory=dict)


#: Typing the entry by its runtime data is what lets every platform read
#: `entry.runtime_data` without a cast.
type UnipolSaiUniboxConfigEntry = ConfigEntry[UnipolSaiUniboxData]


async def async_setup_entry(
    hass: HomeAssistant, entry: UnipolSaiUniboxConfigEntry
) -> bool:
    """Set up an account from a config entry."""
    # A dedicated session: the F5 cookies established at login must persist
    # across every call, and must not leak into Home Assistant's shared one.
    client = UnipolSaiClient(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session=async_create_clientsession(hass),
        **gateway_credentials(entry),
    )

    try:
        vehicles = await client.async_get_vehicles()
    except UnipolSaiAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except UnipolSaiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    if not vehicles:
        raise ConfigEntryNotReady(
            "No vehicle with an active Unibox was found on this account"
        )

    data = UnipolSaiUniboxData(client=client)
    for vehicle in vehicles:
        coordinator = UnipolSaiUniboxCoordinator(hass, entry, client, vehicle)
        await coordinator.async_config_entry_first_refresh()
        data.vehicles[vehicle.plate] = coordinator

        usage = UnipolSaiUniboxUsageCoordinator(hass, entry, client, vehicle)
        await usage.async_config_entry_first_refresh()
        data.usage[vehicle.plate] = usage

    entry.runtime_data = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: UnipolSaiUniboxConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant, entry: UnipolSaiUniboxConfigEntry
) -> None:
    """Reload when the gateway credentials are overridden."""
    await hass.config_entries.async_reload(entry.entry_id)
