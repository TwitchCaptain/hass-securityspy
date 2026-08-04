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

    The client's refresh already carries event-stream runtime state (motion,
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
    """Push-driven coordinator fed by the SecuritySpy event stream."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SecSpyClient,
        *,
        min_score: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,
        )
        self.client = client
        self.entry = entry
        self.min_score = min_score
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
        """Apply an event stream update to camera state and HA."""
        et = event.event_type

        if et == EventType.NULL:
            # Keepalive: every 10s; no state to change, nothing to record.
            return
        if et == EventType.CONNECTED:
            self._stream_connected = True
            self.async_set_updated_data(dict(self.data or self.client.cameras))
            return
        if et in (EventType.DISCONNECTED, EventType.AUTHFAIL):
            self._stream_connected = False
            self.async_set_updated_data(dict(self.data or self.client.cameras))
            if et == EventType.AUTHFAIL and not self._reauth_started:
                # The library has already stopped the watcher for good.
                self._reauth_started = True
                self.entry.async_start_reauth(self.hass)
            return

        cams = dict(self.data or self.client.cameras)
        cam: Camera | None = None
        if event.camera_number is not None and event.camera_number in cams:
            cam = cams[event.camera_number]

        if cam is not None:
            if et in {EventType.TRIGGER_M, EventType.MOTION}:
                cam.motion_active = True
                if event.when:
                    cam.last_motion_time = event.when.isoformat()
                cam.trigger_reasons = list(event.reason_names)
            elif et == EventType.MOTION_END:
                cam.motion_active = False
            elif et == EventType.ONLINE:
                cam.connected = True
            elif et == EventType.OFFLINE:
                cam.connected = False
            elif et == EventType.ARM_M:
                cam.mode_m = "armed"
            elif et == EventType.DISARM_M:
                cam.mode_m = "disarmed"
            elif et == EventType.ARM_C:
                cam.mode_c = "armed"
            elif et == EventType.DISARM_C:
                cam.mode_c = "disarmed"
            elif et == EventType.ARM_A:
                cam.mode_a = "armed"
            elif et == EventType.DISARM_A:
                cam.mode_a = "disarmed"
            elif et == EventType.CLASSIFY:
                # Raw per-class scores are stored unfiltered (-99 = absent in
                # this event); min_score only gates what the event entity
                # fires. Absent scores overwrite older ones so attributes
                # never go stale.
                cam.score_human = event.classify_human
                cam.score_vehicle = event.classify_vehicle
                cam.score_animal = event.classify_animal
                scores = [
                    (label, value)
                    for label, value in (
                        ("human", event.classify_human),
                        ("vehicle", event.classify_vehicle),
                        ("animal", event.classify_animal),
                    )
                    if value >= 0
                ]
                cam.event_object = (
                    max(scores, key=lambda item: item[1])[0] if scores else None
                )
                if event.when:
                    cam.last_motion_time = event.when.isoformat()

        if et == EventType.REFRESH and self.client.info is not None:
            # The library refresh already preserved runtime motion fields.
            cams = dict(self.client.cameras)

        self.async_set_updated_data(cams)

        # Event bus for power users / device automations
        bus_data: dict[str, Any] = {
            "type": et.value,
            "event_id": event.event_id,
            "camera_number": event.camera_number,
            "msg": event.msg,
            "reasons": event.reason_names,
            "score_human": event.classify_human,
            "score_vehicle": event.classify_vehicle,
            "score_animal": event.classify_animal,
            "config_entry_id": self.entry.entry_id,
        }
        if cam is not None:
            bus_data["camera_name"] = cam.name
        self.hass.bus.async_fire(EVENT_BUS_TYPE, bus_data)
