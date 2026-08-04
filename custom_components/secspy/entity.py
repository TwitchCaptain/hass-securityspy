"""Shared entity base for secspy."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from aiosecspy import Camera
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_BRAND, DOMAIN
from .coordinator import SecSpyCoordinator

EntityFactory = Callable[[int], Iterable[Entity]]


@callback
def async_add_camera_entities(
    coordinator: SecSpyCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: EntityFactory,
) -> None:
    """Create entities for current cameras, and for any that appear later.

    SecuritySpy config changes (CONFIGCHANGE -> library refresh) can introduce
    new cameras at runtime; the coordinator listener diffs the camera numbers
    and builds entities for newcomers so a reload is not required.
    """
    known: set[int] = set()

    @callback
    def _sync_entities() -> None:
        new = [number for number in (coordinator.data or {}) if number not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(entity for number in new for entity in factory(number))

    coordinator.entry.async_on_unload(coordinator.async_add_listener(_sync_entities))
    _sync_entities()


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
        """Attach the entity to one camera device with a stable unique id."""
        super().__init__(coordinator)
        self.camera_number = camera_number
        server_id = (
            coordinator.client.info.uuid if coordinator.client.info else "unknown"
        )
        self._attr_unique_id = f"{server_id}|cam{camera_number}|{key}"
        cam = self.camera
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{server_id}_{camera_number}")},
            name=cam.name if cam else f"Camera {camera_number}",
            manufacturer=DEFAULT_BRAND,
            model="SecuritySpy Camera",
            via_device=(DOMAIN, server_id),
            sw_version=coordinator.client.info.version
            if coordinator.client.info
            else None,
        )

    @property
    def camera(self) -> Camera | None:
        """Current camera state."""
        return self.coordinator.data.get(self.camera_number)

    @property
    def available(self) -> bool:
        """Available while the camera exists on the server.

        Stream health is deliberately not part of availability: during a brief
        reconnect the last-known camera state is still the best answer, and the
        "Event stream" diagnostic sensor reports the outage explicitly.
        """
        return super().available and self.camera is not None


class SecSpyServerEntity(CoordinatorEntity[SecSpyCoordinator], Entity):
    """Base entity for the NVR/server device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SecSpyCoordinator, *, key: str) -> None:
        """Attach the entity to the server device."""
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
