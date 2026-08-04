"""Config flow for secspy."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiosecspy import SecSpyClient
from aiosecspy.exceptions import AuthenticationError, RequestError
from awesomeversion import AwesomeVersion
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DISABLE_RTSP,
    CONF_MIN_SCORE,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_MIN_SCORE,
    DEFAULT_PORT,
    DOMAIN,
    MIN_SECSPY_VERSION,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_USE_SSL, default=False): bool,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


class SecSpyVersionError(Exception):
    """Raised when SecuritySpy is older than the supported minimum."""


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate credentials and return server identifiers."""
    session = async_get_clientsession(hass, verify_ssl=data.get(CONF_VERIFY_SSL, True))
    client = SecSpyClient(
        data[CONF_HOST],
        data[CONF_PORT],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        use_ssl=data.get(CONF_USE_SSL, False),
        verify_ssl=data.get(CONF_VERIFY_SSL, True),
        session=session,
    )
    info = await client.refresh()
    if AwesomeVersion(info.version) < AwesomeVersion(MIN_SECSPY_VERSION):
        raise SecSpyVersionError(info.version)
    return {"title": info.name, "uuid": info.uuid, "version": info.version}


class SecSpyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SecuritySpy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _validate_input(self.hass, user_input)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except RequestError:
                errors["base"] = "cannot_connect"
            except SecSpyVersionError:
                errors["base"] = "version_old"
            except Exception:
                _LOGGER.exception("Unexpected error validating SecuritySpy")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["uuid"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                    options={
                        CONF_DISABLE_RTSP: True,
                        CONF_MIN_SCORE: DEFAULT_MIN_SCORE,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle a reauth request (bad or changed credentials)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect new credentials and swap them into the existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                info = await _validate_input(self.hass, data)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except RequestError:
                errors["base"] = "cannot_connect"
            except SecSpyVersionError as err:
                _LOGGER.warning("SecuritySpy too old during reauth: %s", err)
                errors["base"] = "version_old"
            except Exception:
                _LOGGER.exception("Unexpected error validating SecuritySpy")
                errors["base"] = "unknown"
            else:
                # Guard against pointing the entry at a different server (for
                # example after a host/DHCP change put another NVR on this
                # address): the uuid must match the one this entry was made for.
                await self.async_set_unique_id(info["uuid"])
                self._abort_if_unique_id_mismatch(reason="wrong_server")
                return self.async_update_reload_and_abort(entry, data_updates=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow handler."""
        return SecSpyOptionsFlowHandler()


class SecSpyOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Handle options; the entry reloads automatically when they change."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DISABLE_RTSP,
                        default=self.config_entry.options.get(CONF_DISABLE_RTSP, True),
                    ): bool,
                    vol.Optional(
                        CONF_MIN_SCORE,
                        default=self.config_entry.options.get(
                            CONF_MIN_SCORE, DEFAULT_MIN_SCORE
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                }
            ),
        )
