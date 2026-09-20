"""Small helpers shared by setup and the config flow."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_TENANT,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
)


def gateway_credentials(entry: ConfigEntry) -> tuple[str, str, str]:
    """Resolve the gateway credentials: options, then data, then defaults.

    Options win so a user can paste new values if Unipol rotates them, without
    waiting for a release. `data` is checked for entries created before the
    defaults existed, when the flow asked for all three up front.
    """
    return (
        entry.options.get(CONF_CLIENT_ID)
        or entry.data.get(CONF_CLIENT_ID)
        or DEFAULT_CLIENT_ID,
        entry.options.get(CONF_CLIENT_SECRET)
        or entry.data.get(CONF_CLIENT_SECRET)
        or DEFAULT_CLIENT_SECRET,
        entry.options.get(CONF_TENANT) or entry.data.get(CONF_TENANT) or DEFAULT_TENANT,
    )
