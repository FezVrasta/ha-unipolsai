"""Helpers shared by setup and the config flow."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from pyunipolsai import DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET, DEFAULT_TENANT

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_TENANT


def gateway_credentials(entry: ConfigEntry) -> dict[str, str]:
    """Resolve the API gateway credentials.

    Options win over data so a rotation on Unipol's side can be fixed from the
    UI without waiting for a release; `data` is only consulted for entries
    created by the original flow, which asked for all three up front.
    """
    return {
        "client_id": entry.options.get(CONF_CLIENT_ID)
        or entry.data.get(CONF_CLIENT_ID)
        or DEFAULT_CLIENT_ID,
        "client_secret": entry.options.get(CONF_CLIENT_SECRET)
        or entry.data.get(CONF_CLIENT_SECRET)
        or DEFAULT_CLIENT_SECRET,
        "tenant": entry.options.get(CONF_TENANT)
        or entry.data.get(CONF_TENANT)
        or DEFAULT_TENANT,
    }
