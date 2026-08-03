"""The secspy (SecuritySpy) Home Assistant integration."""

from __future__ import annotations

import logging
from pathlib import Path

import homeassistant.helpers.device_registry as dr
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .aiosecspy import CameraMode, SecSpyClient
from .aiosecspy.exceptions import AuthenticationError, RequestError
from .const import (
    ATTR_ENABLED,
    ATTR_MODE,
    ATTR_OVERRIDE_ID,
    ATTR_PRESET_ID,
    ATTR_SCHEDULE_ID,
    CONF_DISABLE_RTSP,
    CONF_MIN_SCORE,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_BRAND,
    DEFAULT_MIN_SCORE,
    DOMAIN,
    MODE_ACTION,
    MODE_CONTINUOUS,
    MODE_MOTION,
    PLATFORMS,
    SERVICE_DOWNLOAD_LATEST_MOTION_RECORDING,
    SERVICE_ENABLE_SCHEDULE_PRESET,
    SERVICE_SET_ARM_MODE,
    SERVICE_SET_SCHEDULE,
    SERVICE_SET_SCHEDULE_OVERRIDE,
    SERVICE_TRIGGER_MOTION,
    VALID_ARM_MODES,
)
from .coordinator import (
    SecSpyCoordinator,
    SecSpyRuntimeData,
    preserve_runtime_camera_state,
)

_LOGGER = logging.getLogger(__name__)

type SecSpyConfigEntry = ConfigEntry[SecSpyRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SecSpyConfigEntry) -> bool:
    """Set up SecuritySpy from a config entry."""
    session = async_get_clientsession(
        hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True)
    )
    client = SecSpyClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        use_ssl=entry.data.get(CONF_USE_SSL, False),
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
        session=session,
    )

    try:
        server_info = await client.refresh()
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed("Invalid SecuritySpy credentials") from err
    except RequestError as err:
        raise ConfigEntryNotReady(f"Cannot connect to SecuritySpy: {err}") from err

    min_score = entry.options.get(CONF_MIN_SCORE, DEFAULT_MIN_SCORE)
    coordinator = SecSpyCoordinator(hass, entry, client, min_score=min_score)
    await coordinator.async_setup()

    entry.runtime_data = SecSpyRuntimeData(
        client=client,
        coordinator=coordinator,
        server_info=server_info,
        disable_rtsp=entry.options.get(CONF_DISABLE_RTSP, True),
        min_score=min_score,
    )

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, server_info.uuid)},
        manufacturer=DEFAULT_BRAND,
        name=server_info.name,
        model="SecuritySpy Server",
        sw_version=server_info.version,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SecSpyConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.coordinator.async_shutdown()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_ENABLE_SCHEDULE_PRESET):
        return

    def _runtime_for_entry_id(entry_id: str | None) -> SecSpyRuntimeData:
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
            and (entry_id is None or e.entry_id == entry_id)
        ]
        if not entries:
            raise HomeAssistantError("No loaded SecuritySpy config entry")
        if entry_id is None and len(entries) > 1:
            raise HomeAssistantError(
                "Multiple SecuritySpy entries loaded; pass config_entry_id"
            )
        return entries[0].runtime_data

    async def handle_enable_preset(call: ServiceCall) -> None:
        runtime = _runtime_for_entry_id(call.data.get("config_entry_id"))
        await runtime.client.set_schedule_preset(int(call.data[ATTR_PRESET_ID]))
        await runtime.client.refresh()
        runtime.coordinator.async_set_updated_data(
            preserve_runtime_camera_state(
                dict(runtime.coordinator.data or {}),
                dict(runtime.client.cameras),
            )
        )

    async def handle_set_arm_mode(call: ServiceCall) -> None:
        entity_id = call.data.get("entity_id")
        if not entity_id:
            raise HomeAssistantError("entity_id is required")
        camera_number = _camera_number_from_entity(hass, entity_id)
        runtime = _runtime_from_entity(hass, entity_id)
        mode = call.data[ATTR_MODE]
        enabled = call.data[ATTR_ENABLED]
        if mode == MODE_MOTION:
            await runtime.client.toggle_motion(camera_number, enabled)
        elif mode == MODE_ACTION:
            await runtime.client.toggle_actions(camera_number, enabled)
        elif mode == MODE_CONTINUOUS:
            await runtime.client.toggle_continuous(camera_number, enabled)
        else:
            raise HomeAssistantError(f"Unsupported mode: {mode}")
        await runtime.client.refresh()
        runtime.coordinator.async_set_updated_data(
            preserve_runtime_camera_state(
                dict(runtime.coordinator.data or {}),
                dict(runtime.client.cameras),
            )
        )

    async def handle_trigger_motion(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        camera_number = _camera_number_from_entity(hass, entity_id)
        runtime = _runtime_from_entity(hass, entity_id)
        await runtime.client.trigger_motion(camera_number)

    async def handle_set_schedule(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        camera_number = _camera_number_from_entity(hass, entity_id)
        runtime = _runtime_from_entity(hass, entity_id)
        mode = CameraMode(str(call.data[ATTR_MODE]).upper())
        await runtime.client.set_schedule(
            camera_number, mode, int(call.data[ATTR_SCHEDULE_ID])
        )
        await runtime.client.refresh()
        runtime.coordinator.async_set_updated_data(
            preserve_runtime_camera_state(
                dict(runtime.coordinator.data or {}),
                dict(runtime.client.cameras),
            )
        )

    async def handle_set_override(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        camera_number = _camera_number_from_entity(hass, entity_id)
        runtime = _runtime_from_entity(hass, entity_id)
        mode = CameraMode(str(call.data[ATTR_MODE]).upper())
        await runtime.client.set_schedule_override(
            camera_number, mode, int(call.data[ATTR_OVERRIDE_ID])
        )
        await runtime.client.refresh()
        runtime.coordinator.async_set_updated_data(
            preserve_runtime_camera_state(
                dict(runtime.coordinator.data or {}),
                dict(runtime.client.cameras),
            )
        )

    async def handle_download(call: ServiceCall) -> None:
        entity_id = call.data["entity_id"]
        filename = call.data["filename"]
        camera_number = _camera_number_from_entity(hass, entity_id)
        runtime = _runtime_from_entity(hass, entity_id)
        data = await runtime.client.download_latest_motion_recording(camera_number)
        path = Path(filename)
        if not path.is_absolute():
            path = Path(hass.config.path(filename))
        if not hass.config.is_allowed_path(str(path)):
            raise HomeAssistantError(f"Path is not allowed: {path}")

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await hass.async_add_executor_job(_write)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE_SCHEDULE_PRESET,
        handle_enable_preset,
        schema=vol.Schema(
            {
                vol.Required(ATTR_PRESET_ID): vol.Coerce(int),
                vol.Optional("config_entry_id"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ARM_MODE,
        handle_set_arm_mode,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): cv.entity_id,
                vol.Required(ATTR_MODE): vol.In(VALID_ARM_MODES),
                vol.Required(ATTR_ENABLED): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER_MOTION,
        handle_trigger_motion,
        schema=vol.Schema({vol.Required("entity_id"): cv.entity_id}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        handle_set_schedule,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): cv.entity_id,
                vol.Required(ATTR_MODE): vol.In(["C", "M", "A", "X", "c", "m", "a", "x"]),
                vol.Required(ATTR_SCHEDULE_ID): vol.Coerce(int),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE_OVERRIDE,
        handle_set_override,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): cv.entity_id,
                vol.Required(ATTR_MODE): vol.In(["C", "M", "A", "X", "c", "m", "a", "x"]),
                vol.Required(ATTR_OVERRIDE_ID): vol.Coerce(int),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD_LATEST_MOTION_RECORDING,
        handle_download,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): cv.entity_id,
                vol.Required("filename"): cv.string,
            }
        ),
    )


def _camera_number_from_entity(hass: HomeAssistant, entity_id: str) -> int:
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.unique_id is None:
        raise HomeAssistantError(f"Unknown entity: {entity_id}")
    # unique_id: {server}|cam{camera_number}|{key}
    parts = entry.unique_id.rsplit("|", 2)
    if len(parts) != 3 or not parts[1].startswith("cam"):
        raise HomeAssistantError(f"Entity is not a secspy camera entity: {entity_id}")
    try:
        return int(parts[1].removeprefix("cam"))
    except ValueError as err:
        raise HomeAssistantError(
            f"Cannot parse camera number from {entity_id}"
        ) from err


def _runtime_from_entity(hass: HomeAssistant, entity_id: str) -> SecSpyRuntimeData:
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.config_entry_id is None:
        raise HomeAssistantError(f"Unknown entity: {entity_id}")
    config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
    if (
        config_entry is None
        or config_entry.state is not ConfigEntryState.LOADED
        or not isinstance(getattr(config_entry, "runtime_data", None), SecSpyRuntimeData)
    ):
        raise HomeAssistantError("SecuritySpy config entry is not loaded")
    return config_entry.runtime_data
