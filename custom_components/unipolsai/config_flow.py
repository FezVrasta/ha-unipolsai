"""Config flow for the UnipolSai Unibox integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import UnipolSaiApi, UnipolSaiAuthError, UnipolSaiError
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_TENANT,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
    DOMAIN,
)
from .helpers import gateway_credentials

_LOGGER = logging.getLogger(__name__)

_PASSWORD_FIELD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _gateway_schema(client_id: str, secret: str, tenant: str) -> dict:
    return {
        vol.Required(CONF_CLIENT_ID, default=client_id): str,
        vol.Required(CONF_CLIENT_SECRET, default=secret): _PASSWORD_FIELD,
        vol.Required(CONF_TENANT, default=tenant): _PASSWORD_FIELD,
    }


async def _validate(
    hass, username: str, password: str, client_id: str, secret: str, tenant: str
) -> tuple[str | None, int]:
    """Return (error_key, vehicle_count)."""
    session = async_create_clientsession(hass)
    api = UnipolSaiApi(session, username, password, client_id, secret, tenant)
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


class UnipolSaiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials.

        Only username and password by default. The gateway credentials ship as
        defaults and are surfaced here only in HA's advanced mode; otherwise
        they live in the options flow.
        """
        errors: dict[str, str] = {}
        schema: dict = {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): _PASSWORD_FIELD,
        }
        if self.show_advanced_options:
            schema |= _gateway_schema(
                DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET, DEFAULT_TENANT
            )

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            client_id = user_input.get(CONF_CLIENT_ID, DEFAULT_CLIENT_ID)
            secret = user_input.get(CONF_CLIENT_SECRET, DEFAULT_CLIENT_SECRET)
            tenant = user_input.get(CONF_TENANT, DEFAULT_TENANT)

            error, count = await _validate(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                client_id,
                secret,
                tenant,
            )
            if error:
                errors["base"] = error
            else:
                _LOGGER.debug("Found %s vehicle(s) with an active box", count)
                options = {}
                # Only persist overrides; defaults stay in code so a future
                # release can correct them.
                if client_id != DEFAULT_CLIENT_ID:
                    options[CONF_CLIENT_ID] = client_id
                if secret != DEFAULT_CLIENT_SECRET:
                    options[CONF_CLIENT_SECRET] = secret
                if tenant != DEFAULT_TENANT:
                    options[CONF_TENANT] = tenant
                return self.async_create_entry(
                    title=f"UnipolSai ({user_input[CONF_USERNAME]})",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options=options,
                )

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(schema), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            error, _ = await _validate(
                self.hass,
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                *gateway_credentials(entry),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_FIELD}),
            errors=errors,
            description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Expose the gateway credentials for override."""
        return UnipolSaiOptionsFlow()


class UnipolSaiOptionsFlow(OptionsFlow):
    """Override the gateway credentials if Unipol rotates them."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the gateway credentials."""
        errors: dict[str, str] = {}
        entry = self.config_entry
        current = gateway_credentials(entry)

        if user_input is not None:
            error, _ = await _validate(
                self.hass,
                entry.data[CONF_USERNAME],
                entry.data[CONF_PASSWORD],
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
                user_input[CONF_TENANT],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_gateway_schema(*current)),
            errors=errors,
        )
