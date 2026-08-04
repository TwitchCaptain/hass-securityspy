"""Coordinator and runtime helpers for secspy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiosecspy import Camera, Event, EventType, SecSpyClient, ServerInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, EVENT_BUS_TYPE

_LOGGER = logging.getLogger(__name__)


async def async_refresh_camera_state(coordinator: SecSpyCoordinator) -> None:
    """Refresh ++systemInfo and push the new camera map to every entity.

    The client's refresh carries event-stream runtime state (motion,
    classification) onto the new camera objects, so this is the one call
    mutating services need after talking to SecuritySpy.
    """
    await coordinator.client.refresh()
    coordinator.async_set_updated_data(dict(coordinator.client.cameras))


@dataclass
class SecSpyRuntimeData:
    """Runtime objects stored on the config entry."""

    client: SecSpyClient
    coordinator: SecSpyCoordinator
    server_info: ServerInfo
    disable_rtsp: bool
    min_score: int


class SecSpyCoordinator(DataUpdateCoordinator[dict[int, Camera]]):
    """Push-driven coordinator fed by the SecuritySpy event stream.

    The aiosecspy event stream already folds every wire event into the
    client's Camera objects before listeners run, so this coordinator only
    pushes fresh snapshots of that state to entities, tracks stream health,
    and mirrors events onto the HA event bus.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SecSpyClient,
    ) -> None:
        """Wire the coordinator to one config entry and its client."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,
        )
        self.client = client
        self.entry = entry
        self._unsub_stream = None
        self._stream_connected = False
        self._reauth_started = False

    @property
    def stream_connected(self) -> bool:
        """Whether the event stream is currently connected."""
        return self._stream_connected

    async def async_setup(self) -> None:
        """Seed camera state and start the event stream."""
        if self.client.info is None:
            await self.client.refresh()
        self.async_set_updated_data(dict(self.client.cameras))
        self._unsub_stream = self.client.events.add_listener(self._on_event)
        self.client.events.start(refresh_on_config_change=True)

    async def async_shutdown(self) -> None:
        """Stop stream listeners."""
        if self._unsub_stream:
            self._unsub_stream()
            self._unsub_stream = None
        await self.client.events.stop()
        await super().async_shutdown()

    async def _on_event(self, event: Event) -> None:
        """Push the library-maintained camera state into HA for one event."""
        et = event.event_type

        if et is EventType.NULL:
            # Keepalive: every 10s; no state to change, nothing to record.
            return
        if et is EventType.CONNECTED:
            self._stream_connected = True
            self.async_set_updated_data(dict(self.client.cameras))
            return
        if et in (EventType.DISCONNECTED, EventType.AUTHFAIL):
            self._stream_connected = False
            self.async_set_updated_data(dict(self.client.cameras))
            if et is EventType.AUTHFAIL and not self._reauth_started:
                # The library has already stopped the watcher for good.
                self._reauth_started = True
                self.entry.async_start_reauth(self.hass)
            return

        # The library applied the event to client.cameras before we ran (and
        # a REFRESH means it re-read ++systemInfo), so a snapshot of that map
        # is always the freshest state available.
        self.async_set_updated_data(dict(self.client.cameras))

        # Event bus for power users / device automations. Keys match the
        # entity attribute names (trigger_reasons, event_score_*).
        cam = (
            self.client.cameras.get(event.camera_number)
            if event.camera_number is not None
            else None
        )
        bus_data: dict[str, Any] = {
            "type": et.value,
            "event_id": event.event_id,
            "camera_number": event.camera_number,
            "msg": event.msg,
            "trigger_reasons": event.reason_names,
            "event_score_human": event.classify_human,
            "event_score_vehicle": event.classify_vehicle,
            "event_score_animal": event.classify_animal,
            "config_entry_id": self.entry.entry_id,
        }
        if cam is not None:
            bus_data["camera_name"] = cam.name
        self.hass.bus.async_fire(EVENT_BUS_TYPE, bus_data)
