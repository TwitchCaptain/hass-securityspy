"""Shared entity base for secspy."""

from __future__ import annotations

from aiosecspy import Camera
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_BRAND, DOMAIN
from .coordinator import SecSpyCoordinator


class SecSpyBaseEntity(CoordinatorEntity[SecSpyCoordinator], Entity):
    """Base entity tied to a SecuritySpy camera device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SecSpyCoordinator,
        camera_number: int,
        *,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self.camera_number = camera_number
        server_id = coordinator.client.info.uuid if coordinator.client.info else "unknown"
        self._attr_unique_id = f"{server_id}|cam{camera_number}|{key}"
        cam = self.camera
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{server_id}_{camera_number}")},
            name=cam.name if cam else f"Camera {camera_number}",
            manufacturer=DEFAULT_BRAND,
            model="SecuritySpy Camera",
            via_device=(DOMAIN, server_id),
            sw_version=coordinator.client.info.version if coordinator.client.info else None,
        )

    @property
    def camera(self) -> Camera | None:
        """Current camera state."""
        return self.coordinator.data.get(self.camera_number)

    @property
    def available(self) -> bool:
        """Entity is available when coordinator has camera data."""
        return self.camera is not None


class SecSpyServerEntity(CoordinatorEntity[SecSpyCoordinator], Entity):
    """Base entity for the NVR/server device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SecSpyCoordinator, *, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.client.info
        server_id = info.uuid if info else "unknown"
        self._attr_unique_id = f"{server_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, server_id)},
            name=info.name if info else "SecuritySpy",
            manufacturer=DEFAULT_BRAND,
            model="SecuritySpy Server",
            sw_version=info.version if info else None,
        )
