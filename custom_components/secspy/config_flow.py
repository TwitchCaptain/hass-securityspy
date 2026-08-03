"""Config flow for secspy."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from awesomeversion import AwesomeVersion
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .aiosecspy import SecSpyClient
from .aiosecspy.exceptions import AuthenticationError, RequestError
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
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_USE_SSL, default=False): bool,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


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
        raise ValueError("version_old")
    return {"title": info.name, "uuid": info.uuid, "version": info.version}


class SecSpyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SecuritySpy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _validate_input(self.hass, user_input)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except RequestError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "version_old"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating SecuritySpy")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["uuid"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                    options={
                        CONF_DISABLE_RTSP: False,
                        CONF_MIN_SCORE: DEFAULT_MIN_SCORE,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow handler."""
        return SecSpyOptionsFlowHandler()


class SecSpyOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DISABLE_RTSP,
                        default=self.config_entry.options.get(CONF_DISABLE_RTSP, False),
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
