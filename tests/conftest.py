"""Shared fixtures for secspy component tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from pytest_homeassistant_custom_component.common import MockConfigEntry


# pytest-homeassistant-custom-component 0.13.x defines `enable_event_loop_debug`
# as a plain `@pytest.fixture(autouse=True)` async generator, which pytest 9
# rejects. Override it locally until the upstream plugin handles pytest 9.
@pytest_asyncio.fixture(autouse=True)
async def enable_event_loop_debug() -> None:
    """Enable event loop debug mode."""
    import asyncio

    asyncio.get_running_loop().set_debug(True)


from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

from custom_components.secspy.const import (
    CONF_DISABLE_RTSP,
    CONF_MIN_SCORE,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

ENTRY_DATA: dict[str, Any] = {
    CONF_HOST: "secspy.local",
    CONF_PORT: 8000,
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
    CONF_USE_SSL: False,
    CONF_VERIFY_SSL: True,
}
ENTRY_OPTIONS: dict[str, Any] = {CONF_DISABLE_RTSP: True, CONF_MIN_SCORE: 50}


@dataclass
class FakeCamera:
    """Minimal stand-in for aiosecspy.Camera."""

    name: str = "Porch"
    connected: bool = True
    motion_active: bool = False
    mode_m: str = "armed"
    mode_c: str = "armed"
    mode_a: str = "disarmed"
    event_object: str | None = None
    score_human: int = -99
    score_vehicle: int = -99
    score_animal: int = -99
    last_motion_time: str | None = None
    trigger_reasons: list[str] = field(default_factory=list)

    @property
    def armed_motion(self) -> bool:
        return self.mode_m == "armed"

    @property
    def armed_actions(self) -> bool:
        return self.mode_a == "armed"

    @property
    def armed_continuous(self) -> bool:
        return self.mode_c == "armed"


def make_client(cameras: dict[int, FakeCamera] | None = None) -> MagicMock:
    """Build a client mock with an event listener registry."""
    client = MagicMock()
    client.cameras = cameras if cameras is not None else {0: FakeCamera()}
    client.info = MagicMock(uuid="server-uuid", version="6.9.0")
    client.refresh = AsyncMock(return_value=client.info)
    client._listeners: list = []

    def _add_listener(cb):
        client._listeners.append(cb)

        def _unsub():
            if cb in client._listeners:
                client._listeners.remove(cb)

        return _unsub

    client.events.add_listener = _add_listener
    client.events.start = MagicMock()
    client.events.stop = AsyncMock()
    return client


async def emit(client: MagicMock, *events) -> None:
    """Dispatch events to every registered listener (sync or async)."""
    import inspect

    for event in events:
        for cb in list(client._listeners):
            result = cb(event)
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
        unique_id="server-uuid",
    )
