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

    def __init__(self, coordinator, camera_number, *, disable_rtsp: bool) -> None:
        Camera.__init__(self)
        SecSpyBaseEntity.__init__(self, coordinator, camera_number, key="camera")
        self._disable_rtsp = disable_rtsp
        if not disable_rtsp:
            self._attr_supported_features = CameraEntityFeature.STREAM
        else:
            self._attr_supported_features = CameraEntityFeature(0)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image."""
        return await self.coordinator.client.get_image(
            self.camera_number, width=width, height=height
        )

    async def stream_source(self) -> str | None:
        """Return stream URL.

        RTSP URLs include userinfo credentials (SecuritySpy requirement). By
        default Disable RTSP is on so MJPEG (auth query) is used; turn it off
        only if you opt into RTSP stream URLs with embedded credentials.
        """
        if self._disable_rtsp:
            return self.coordinator.client.mjpeg_url(self.camera_number)
        return self.coordinator.client.rtsp_url(self.camera_number)

    async def async_enable_motion_detection(self) -> None:
        """Arm motion capture."""
        await self._set_motion(True)

    async def async_disable_motion_detection(self) -> None:
        """Disarm motion capture."""
        await self._set_motion(False)

    async def _set_motion(self, arm: bool) -> None:
        await self.coordinator.client.toggle_motion(self.camera_number, arm)
        cams = dict(self.coordinator.data or {})
        cam = cams.get(self.camera_number)
        if cam is not None:
            cam.mode_m = "armed" if arm else "disarmed"
            self.coordinator.async_set_updated_data(cams)
        else:
            self.async_write_ha_state()
