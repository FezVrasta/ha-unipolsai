"""Config flow for the UnipolSai Unibox integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import UnipolSaiApi, UnipolSaiAuthError, UnipolSaiError
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_TENANT, DOMAIN

_LOGGER = logging.getLogger(__name__)

_PASSWORD_FIELD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): _PASSWORD_FIELD,
        # Not hardcoded: these are the app's IBM API Connect gateway
        # credentials, captured from its cold-start apicConfig call. Unipol
        # can rotate them, so they're configuration rather than constants.
        # docs/CAPTURE.md explains how to obtain them.
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): _PASSWORD_FIELD,
        vol.Required(CONF_TENANT): _PASSWORD_FIELD,
    }
)


class UnipolSaiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry_data: Mapping[str, Any] | None = None

    async def _validate(self, data: Mapping[str, Any]) -> tuple[str | None, int]:
        """Return (error, vehicle_count)."""
        session = async_create_clientsession(self.hass)
        api = UnipolSaiApi(
            session,
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            data[CONF_CLIENT_ID],
            data[CONF_CLIENT_SECRET],
            data[CONF_TENANT],
        )
        try:
            await api.login()
            contracts = await api.telematic_contracts()
        except UnipolSaiAuthError:
            return "invalid_auth", 0
        except UnipolSaiError as err:
            _LOGGER.debug("Validation failed: %s", err)
            return "cannot_connect", 0
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating UnipolSai credentials")
            return "unknown", 0

        active = [c for c in contracts if c.get("statoTerminale") == "active"]
        if not active:
            return "no_vehicles", 0
        return None, len(active)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            error, count = await self._validate(user_input)
            if error:
                errors["base"] = error
            else:
                _LOGGER.debug("Found %s vehicle(s) with an active box", count)
                return self.async_create_entry(
                    title=f"UnipolSai ({user_input[CONF_USERNAME]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        self._reauth_entry_data = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            data = {**entry.data, **user_input}
            error, _ = await self._validate(data)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_FIELD}),
            errors=errors,
            description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
        )
