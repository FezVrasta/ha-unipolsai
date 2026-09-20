"""Config flow."""

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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from pyunipolsai import (
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_TENANT,
    UnipolSaiAuthError,
    UnipolSaiClient,
    UnipolSaiError,
)

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_TENANT, DOMAIN
from .helpers import gateway_credentials

_LOGGER = logging.getLogger(__name__)

PASSWORD_FIELD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _gateway_schema(
    client_id: str, client_secret: str, tenant: str
) -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_CLIENT_ID, default=client_id): str,
        vol.Required(CONF_CLIENT_SECRET, default=client_secret): PASSWORD_FIELD,
        vol.Required(CONF_TENANT, default=tenant): PASSWORD_FIELD,
    }


async def _validate(
    hass: HomeAssistant, username: str, password: str, **gateway: str
) -> tuple[str | None, int]:
    """Try the credentials. Returns an error key and the vehicle count."""
    client = UnipolSaiClient(
        username, password, session=async_create_clientsession(hass), **gateway
    )
    try:
        vehicles = await client.async_get_vehicles()
    except UnipolSaiAuthError:
        return "invalid_auth", 0
    except UnipolSaiError as err:
        _LOGGER.debug("Validation failed: %s", err)
        return "cannot_connect", 0
    except Exception:
        _LOGGER.exception("Unexpected error validating credentials")
        return "unknown", 0

    if not vehicles:
        return "no_vehicles", 0
    return None, len(vehicles)


class UnipolSaiUniboxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the account credentials.

        Only username and password by default. The gateway credentials ship
        with the library and appear here only in advanced mode; otherwise
        they live in the options flow, for the day Unipol rotates them.
        """
        errors: dict[str, str] = {}
        schema: dict[vol.Marker, Any] = {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): PASSWORD_FIELD,
        }
        if self.show_advanced_options:
            schema |= _gateway_schema(
                DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET, DEFAULT_TENANT
            )

        if user_input is not None:
            # The account is the identity here: there is no device to key on
            # until we have talked to it.
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            gateway = {
                "client_id": user_input.get(CONF_CLIENT_ID, DEFAULT_CLIENT_ID),
                "client_secret": user_input.get(
                    CONF_CLIENT_SECRET, DEFAULT_CLIENT_SECRET
                ),
                "tenant": user_input.get(CONF_TENANT, DEFAULT_TENANT),
            }
            error, count = await _validate(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                **gateway,
            )
            if error:
                errors["base"] = error
            else:
                _LOGGER.debug("Found %s vehicle(s) with an active box", count)
                # Only overrides are persisted, so a corrected default in a
                # future release reaches existing installs.
                options = {
                    key: value
                    for key, value, default in (
                        (CONF_CLIENT_ID, gateway["client_id"], DEFAULT_CLIENT_ID),
                        (
                            CONF_CLIENT_SECRET,
                            gateway["client_secret"],
                            DEFAULT_CLIENT_SECRET,
                        ),
                        (CONF_TENANT, gateway["tenant"], DEFAULT_TENANT),
                    )
                    if value != default
                }
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
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
        """Start re-authentication."""
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
                **gateway_credentials(entry),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_FIELD}),
            errors=errors,
            description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the account this entry uses."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            # Pointing an entry at a different account would merge two
            # vehicles' histories into one set of entities.
            self._abort_if_unique_id_mismatch(reason="wrong_account")

            error, _ = await _validate(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                **gateway_credentials(entry),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=entry.data.get(CONF_USERNAME)
                    ): str,
                    vol.Required(CONF_PASSWORD): PASSWORD_FIELD,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Expose the gateway credentials for override."""
        return UnipolSaiUniboxOptionsFlow()


class UnipolSaiUniboxOptionsFlow(OptionsFlow):
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
                client_id=user_input[CONF_CLIENT_ID],
                client_secret=user_input[CONF_CLIENT_SECRET],
                tenant=user_input[CONF_TENANT],
            )
            if error:
                errors["base"] = error
            else:
                # Same rule as the initial flow: persist a value only when it
                # differs from the shipped default, so a corrected default in a
                # future release still reaches this entry rather than being
                # pinned to whatever was current when the form was last opened.
                return self.async_create_entry(
                    data={
                        key: value
                        for key, value, default in (
                            (
                                CONF_CLIENT_ID,
                                user_input[CONF_CLIENT_ID],
                                DEFAULT_CLIENT_ID,
                            ),
                            (
                                CONF_CLIENT_SECRET,
                                user_input[CONF_CLIENT_SECRET],
                                DEFAULT_CLIENT_SECRET,
                            ),
                            (CONF_TENANT, user_input[CONF_TENANT], DEFAULT_TENANT),
                        )
                        if value != default
                    }
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                _gateway_schema(
                    current["client_id"], current["client_secret"], current["tenant"]
                )
            ),
            errors=errors,
        )
