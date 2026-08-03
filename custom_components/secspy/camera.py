"""Camera entities for SecuritySpy."""

from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SecSpyBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cameras."""
    runtime = entry.runtime_data
    async_add_entities(
        [
            SecSpyCamera(
                runtime.coordinator,
                cam_num,
                disable_rtsp=runtime.disable_rtsp,
            )
            for cam_num in runtime.coordinator.data
        ]
    )


class SecSpyCamera(SecSpyBaseEntity, Camera):
    """SecuritySpy camera with snapshot and optional RTSP stream."""

    _attr_name = None  # Use device name as entity name
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, camera_number, *, disable_rtsp: bool) -> None:
        Camera.__init__(self)
        SecSpyBaseEntity.__init__(self, coordinator, camera_number, key="camera")
        self._disable_rtsp = disable_rtsp

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image."""
        return await self.coordinator.client.get_image(
            self.camera_number, width=width, height=height
        )

    async def stream_source(self) -> str | None:
        """Return stream URL."""
        if self._disable_rtsp:
            return self.coordinator.client.mjpeg_url(self.camera_number)
        return self.coordinator.client.rtsp_url(self.camera_number)

    async def async_enable_motion_detection(self) -> None:
        """Arm motion capture."""
        await self.coordinator.client.toggle_motion(self.camera_number, True)
        if self.camera:
            self.camera.mode_m = "armed"
        self.async_write_ha_state()

    async def async_disable_motion_detection(self) -> None:
        """Disarm motion capture."""
        await self.coordinator.client.toggle_motion(self.camera_number, False)
        if self.camera:
            self.camera.mode_m = "disarmed"
        self.async_write_ha_state()
