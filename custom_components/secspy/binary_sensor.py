"""Binary sensors for SecuritySpy cameras and the server."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_EVENT_OBJECT,
    ATTR_EVENT_SCORE_ANIMAL,
    ATTR_EVENT_SCORE_HUMAN,
    ATTR_EVENT_SCORE_VEHICLE,
    ATTR_LAST_TRIP_TIME,
    ATTR_TRIGGER_REASONS,
)
from .entity import SecSpyBaseEntity, SecSpyServerEntity, async_add_camera_entities

if TYPE_CHECKING:
    from . import SecSpyConfigEntry
    from .coordinator import SecSpyCoordinator

BINARY_SENSORS = (
    BinarySensorEntityDescription(
        key="motion",
        translation_key="motion",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    BinarySensorEntityDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SecSpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    runtime = entry.runtime_data
    async_add_entities([SecSpyStreamSensor(runtime.coordinator)])
    async_add_camera_entities(
        runtime.coordinator,
        async_add_entities,
        lambda number: [
            SecSpyBinarySensor(runtime.coordinator, number, description)
            for description in BINARY_SENSORS
        ],
    )


class SecSpyBinarySensor(SecSpyBaseEntity, BinarySensorEntity):
    """Motion / online binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: SecSpyCoordinator,
        camera_number: int,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Bind the description to one camera."""
        super().__init__(coordinator, camera_number, key=description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return sensor state."""
        cam = self.camera
        if cam is None:
            return False
        if self.entity_description.key == "motion":
            return cam.motion_active
        return cam.connected

    @property
    def extra_state_attributes(self) -> dict | None:
        """Extra attributes for motion sensor."""
        cam = self.camera
        if cam is None or self.entity_description.key != "motion":
            return None
        return {
            ATTR_LAST_TRIP_TIME: cam.last_motion_time,
            ATTR_EVENT_OBJECT: cam.event_object,
            ATTR_EVENT_SCORE_HUMAN: cam.score_human,
            ATTR_EVENT_SCORE_VEHICLE: cam.score_vehicle,
            ATTR_EVENT_SCORE_ANIMAL: cam.score_animal,
            ATTR_TRIGGER_REASONS: cam.trigger_reasons,
        }


class SecSpyStreamSensor(SecSpyServerEntity, BinarySensorEntity):
    """Health of the SecuritySpy event stream, on the server device.

    Camera entities stay available through brief stream reconnects; this
    sensor is where an outage becomes visible (and alertable).
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "event_stream"

    def __init__(self, coordinator: SecSpyCoordinator) -> None:
        """Attach to the server device."""
        super().__init__(coordinator, key="event_stream")

    @property
    def is_on(self) -> bool:
        """Return whether the event stream is connected."""
        return self.coordinator.stream_connected
