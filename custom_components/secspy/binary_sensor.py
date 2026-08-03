"""Binary sensors for SecuritySpy cameras."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
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
from .entity import SecSpyBaseEntity


BINARY_SENSORS = (
    BinarySensorEntityDescription(
        key="motion",
        name="Motion",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    BinarySensorEntityDescription(
        key="online",
        name="Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    runtime = entry.runtime_data
    entities: list[SecSpyBinarySensor] = []
    for cam_num in runtime.coordinator.data:
        for description in BINARY_SENSORS:
            entities.append(
                SecSpyBinarySensor(runtime.coordinator, cam_num, description)
            )
    async_add_entities(entities)


class SecSpyBinarySensor(SecSpyBaseEntity, BinarySensorEntity):
    """Motion / online binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(self, coordinator, camera_number, description) -> None:
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
