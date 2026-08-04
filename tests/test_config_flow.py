"""Tests for the secspy config, reauth, and options flows."""

from __future__ import annotations

from unittest.mock import patch

from aiosecspy import ServerInfo
from aiosecspy.exceptions import AuthenticationError, RequestError
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.secspy.const import (
    CONF_DISABLE_RTSP,
    CONF_MIN_SCORE,
    DOMAIN,
)

from .conftest import ENTRY_DATA, SERVER_UUID

VALID_INFO = ServerInfo(name="Sec Spy", version="6.9.0", uuid=SERVER_UUID)


def _patch_refresh(result=VALID_INFO, side_effect=None):
    return patch(
        "custom_components.secspy.config_flow.SecSpyClient.refresh",
        return_value=result,
        side_effect=side_effect,
    )


def _patch_setup():
    return patch("custom_components.secspy.async_setup_entry", return_value=True)


async def test_user_flow_creates_entry_with_default_options(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with _patch_refresh(), _patch_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], ENTRY_DATA
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sec Spy"
    assert result["data"] == ENTRY_DATA
    assert result["options"] == {CONF_DISABLE_RTSP: True, CONF_MIN_SCORE: 50}
    assert result["result"].unique_id == SERVER_UUID


async def test_user_flow_maps_errors(hass):
    for side_effect, expected in [
        (AuthenticationError("nope"), "invalid_auth"),
        (RequestError("down"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ]:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        with _patch_refresh(side_effect=side_effect):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], ENTRY_DATA
            )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": expected}


async def test_user_flow_rejects_old_server(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    old = ServerInfo(name="Old", version="4.0.0", uuid=SERVER_UUID)
    with _patch_refresh(result=old):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], ENTRY_DATA
        )
    assert result["errors"] == {"base": "version_old"}


async def test_user_flow_aborts_on_duplicate_server(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_refresh():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], ENTRY_DATA
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_credentials(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with _patch_refresh(), _patch_setup():
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "admin", CONF_PASSWORD: "newpass"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "newpass"


async def test_reauth_rejects_a_different_server(hass, mock_config_entry):
    """A uuid change means the address now points at some other NVR."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)

    other = ServerInfo(name="Other", version="6.9.0", uuid="other-uuid")
    with _patch_refresh(result=other):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "admin", CONF_PASSWORD: "newpass"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_server"
    assert mock_config_entry.data[CONF_PASSWORD] == "secret"


async def test_reauth_keeps_asking_on_bad_credentials(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)

    with _patch_refresh(side_effect=AuthenticationError("nope")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "admin", CONF_PASSWORD: "stillwrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow_updates_options(hass, setup_entry):
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_DISABLE_RTSP: False, CONF_MIN_SCORE: 80},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options == {CONF_DISABLE_RTSP: False, CONF_MIN_SCORE: 80}
