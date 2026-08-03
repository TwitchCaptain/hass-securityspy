"""Coordinator and runtime helpers for secspy."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .aiosecspy import Camera, Event, EventType, SecSpyClient, ServerInfo
from .const import DOMAIN, EVENT_BUS_TYPE

_LOGGER = logging.getLogger(__name__)


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
        self._unsub_stream: Callable[[], None] | None = None
        self._device_callbacks: dict[int, list[Callable[[], None]]] = {}

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

    def async_subscribe_camera(
        self, camera_number: int, callback_fn: Callable[[], None]
    ) -> Callable[[], None]:
        """Subscribe to updates for one camera; returns unsubscribe."""
        self._device_callbacks.setdefault(camera_number, []).append(callback_fn)

        def _unsub() -> None:
            cbs = self._device_callbacks.get(camera_number, [])
            if callback_fn in cbs:
                cbs.remove(callback_fn)

        return _unsub

    @callback
    def _notify_camera(self, camera_number: int | None) -> None:
        if camera_number is None:
            for cbs in self._device_callbacks.values():
                for cb in cbs:
                    cb()
            return
        for cb in self._device_callbacks.get(camera_number, []):
            cb()

    async def _on_event(self, event: Event) -> None:
        """Apply an event stream update to camera state and HA."""
        cams = dict(self.data or self.client.cameras)
        cam: Camera | None = None
        if event.camera_number is not None and event.camera_number in cams:
            cam = cams[event.camera_number]

        et = event.event_type

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
                scores = []
                if event.classify_human >= 0:
                    cam.score_human = event.classify_human
                    scores.append(("human", event.classify_human))
                if event.classify_vehicle >= 0:
                    cam.score_vehicle = event.classify_vehicle
                    scores.append(("vehicle", event.classify_vehicle))
                if event.classify_animal >= 0:
                    cam.score_animal = event.classify_animal
                    scores.append(("animal", event.classify_animal))
                if scores:
                    scores.sort(key=lambda item: item[1], reverse=True)
                    cam.event_object = scores[0][0]
                if event.when:
                    cam.last_motion_time = event.when.isoformat()

        if et == EventType.REFRESH and self.client.info is not None:
            # Preserve runtime motion flags across refresh.
            old = cams
            cams = dict(self.client.cameras)
            for num, new_cam in cams.items():
                if num in old:
                    new_cam.motion_active = old[num].motion_active
                    new_cam.event_object = old[num].event_object
                    new_cam.score_human = old[num].score_human
                    new_cam.score_vehicle = old[num].score_vehicle
                    new_cam.score_animal = old[num].score_animal
                    new_cam.last_motion_time = old[num].last_motion_time
                    new_cam.trigger_reasons = old[num].trigger_reasons

        self.async_set_updated_data(cams)
        self._notify_camera(event.camera_number)

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
