"""Setup, unload, service, and dynamic-camera tests for secspy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.secspy.const import DOMAIN

from .conftest import make_camera


async def test_setup_creates_entities_and_services(hass, setup_entry):
    assert setup_entry.state is ConfigEntryState.LOADED

    registry = er.async_get(hass)
    entities = [
        e
        for e in registry.entities.values()
        if e.config_entry_id == setup_entry.entry_id
    ]
    unique_ids = {e.unique_id for e in entities}
    # Two cameras, each with camera/motion/online/switches/sensors/events.
    assert f"{setup_entry.unique_id}|cam1|camera" in unique_ids
    assert f"{setup_entry.unique_id}|cam2|camera" in unique_ids
    assert f"{setup_entry.unique_id}|cam1|motion" in unique_ids
    assert f"{setup_entry.unique_id}|cam1|arm_motion" in unique_ids
    # The server-level stream health sensor exists.
    assert f"{setup_entry.unique_id}_event_stream" in unique_ids

    for service in (
        "set_arm_mode",
        "trigger_motion",
        "set_schedule",
        "set_schedule_override",
        "enable_schedule_preset",
        "download_latest_motion_recording",
    ):
        assert hass.services.has_service(DOMAIN, service)


async def test_unload_removes_services(hass, setup_entry, mock_client):
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()

    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "set_arm_mode")
    mock_client.events.stop.assert_awaited()


async def test_new_camera_gets_entities_without_reload(hass, setup_entry, mock_client):
    """A camera appearing after a refresh grows entities on the fly."""
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "camera", DOMAIN, f"{setup_entry.unique_id}|cam9|camera"
        )
        is None
    )

    mock_client.cameras[9] = make_camera(9, "New Cam")
    coordinator = setup_entry.runtime_data.coordinator
    coordinator.async_set_updated_data(dict(mock_client.cameras))
    await hass.async_block_till_done()

    assert registry.async_get_entity_id(
        "camera", DOMAIN, f"{setup_entry.unique_id}|cam9|camera"
    )
    assert registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{setup_entry.unique_id}|cam9|motion"
    )


async def test_set_arm_mode_service(hass, setup_entry, mock_client):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "camera", DOMAIN, f"{setup_entry.unique_id}|cam1|camera"
    )
    mock_client.toggle_motion = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        "set_arm_mode",
        {"entity_id": entity_id, "mode": "on_motion", "enabled": True},
        blocking=True,
    )
    mock_client.toggle_motion.assert_awaited_once_with(1, arm=True)


async def test_set_schedule_service_uppercases_mode(hass, setup_entry, mock_client):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "camera", DOMAIN, f"{setup_entry.unique_id}|cam2|camera"
    )
    mock_client.set_schedule = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {"entity_id": entity_id, "mode": "m", "schedule_id": 1},
        blocking=True,
    )
    args = mock_client.set_schedule.await_args.args
    assert args[0] == 2
    assert str(args[1]) == "M"
    assert args[2] == 1


async def test_download_rejects_disallowed_paths(hass, setup_entry, mock_client):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "camera", DOMAIN, f"{setup_entry.unique_id}|cam1|camera"
    )
    mock_client.download_latest_motion_recording = AsyncMock(return_value=b"clip")

    with pytest.raises(HomeAssistantError, match="not allowed"):
        await hass.services.async_call(
            DOMAIN,
            "download_latest_motion_recording",
            {"entity_id": entity_id, "filename": "/etc/passwd"},
            blocking=True,
        )
    mock_client.download_latest_motion_recording.assert_not_awaited()


async def test_download_writes_into_an_allowed_path(
    hass, setup_entry, mock_client, tmp_path
):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "camera", DOMAIN, f"{setup_entry.unique_id}|cam1|camera"
    )
    mock_client.download_latest_motion_recording = AsyncMock(return_value=b"clip")
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    target = tmp_path / "clips" / "latest.m4v"

    await hass.services.async_call(
        DOMAIN,
        "download_latest_motion_recording",
        {"entity_id": entity_id, "filename": str(target)},
        blocking=True,
    )
    assert Path(target).read_bytes() == b"clip"


async def test_service_rejects_foreign_entities(hass, setup_entry):
    with pytest.raises(HomeAssistantError, match="Unknown entity"):
        await hass.services.async_call(
            DOMAIN,
            "trigger_motion",
            {"entity_id": "camera.does_not_exist"},
            blocking=True,
        )
