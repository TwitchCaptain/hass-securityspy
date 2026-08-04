"""Shared fixtures for secspy component tests."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from aiosecspy import Camera, Event, SecSpyClient, ServerInfo
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.secspy.const import (
    CONF_DISABLE_RTSP,
    CONF_MIN_SCORE,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

SERVER_UUID = "server-uuid"


# pytest-homeassistant-custom-component 0.13.x defines `enable_event_loop_debug`
# as a plain `@pytest.fixture(autouse=True)` async generator, which pytest 9
# rejects. Override it locally until the upstream plugin handles pytest 9.
@pytest_asyncio.fixture(autouse=True)
async def enable_event_loop_debug() -> None:
    """Enable event loop debug mode."""
    asyncio.get_running_loop().set_debug(True)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the HA test harness discover custom_components/secspy."""
    return


ENTRY_DATA: dict[str, Any] = {
    CONF_HOST: "secspy.local",
    CONF_PORT: 8000,
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
    CONF_USE_SSL: False,
    CONF_VERIFY_SSL: True,
}
ENTRY_OPTIONS: dict[str, Any] = {CONF_DISABLE_RTSP: True, CONF_MIN_SCORE: 50}


def make_camera(number: int = 0, name: str = "Porch", **kwargs: Any) -> Camera:
    """Build a real aiosecspy Camera with sensible defaults for tests."""
    kwargs.setdefault("connected", True)
    kwargs.setdefault("mode_m", "armed")
    kwargs.setdefault("mode_c", "armed")
    return Camera(number=number, name=name, **kwargs)


def make_client(cameras: dict[int, Camera] | None = None) -> SecSpyClient:
    """Build a real client (never opened) with a seeded ServerInfo."""
    client = SecSpyClient("secspy.local", 8000, "admin", "secret")
    client.info = ServerInfo(
        name="SecuritySpy",
        version="6.9.0",
        uuid=SERVER_UUID,
        cameras=cameras if cameras is not None else {0: make_camera()},
    )
    return client


async def emit(client: SecSpyClient, *events: Event) -> None:
    """Feed events through the library state machine and to every listener.

    Mirrors what the real EventStream reader/dispatcher pair does, without
    needing a network connection.
    """
    for event in events:
        client.events._apply_event(event)
        for callback in list(client.events._callbacks):
            result = callback(event)
            if inspect.isawaitable(result):
                await result


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Config entry with typical user input."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="SecuritySpy",
        data=ENTRY_DATA,
        options=ENTRY_OPTIONS,
        unique_id=SERVER_UUID,
    )


@pytest.fixture
def mock_client() -> MagicMock:
    """A fully mocked SecSpyClient for setup/service tests.

    Uses real Camera/ServerInfo data so entities read genuine state, but every
    network-touching method is an AsyncMock.
    """
    cameras = {
        1: make_camera(1, "Porch"),
        2: make_camera(2, "Garage", mode_a="armed"),
    }
    info = ServerInfo(
        name="SecuritySpy", version="6.9.0", uuid=SERVER_UUID, cameras=cameras
    )
    client = MagicMock(spec=SecSpyClient)
    client.info = info
    client.cameras = cameras
    client.verify_ssl = True
    client.refresh = AsyncMock(return_value=info)
    client.rtsp_url = MagicMock(
        return_value="rtsp://admin:secret@secspy.local:8000/stream?cameraNum=1"
    )
    client.mjpeg_url = MagicMock(return_value="http://secspy.local:8000/++video")

    listeners: list = []

    def _add_listener(callback):
        listeners.append(callback)

        def _unsub() -> None:
            if callback in listeners:
                listeners.remove(callback)

        return _unsub

    client.events = MagicMock()
    client.events._callbacks = listeners
    client.events.add_listener = _add_listener
    client.events.start = MagicMock()
    client.events.stop = AsyncMock()
    return client


@pytest.fixture
async def setup_entry(hass, mock_config_entry, mock_client) -> MockConfigEntry:
    """Set the integration up fully against the mocked client."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.secspy.SecSpyClient", return_value=mock_client):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry
