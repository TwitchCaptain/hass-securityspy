"""Sensors for SecuritySpy cameras."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_EVENT_SCORE_ANIMAL,
    ATTR_EVENT_SCORE_HUMAN,
    ATTR_EVENT_SCORE_VEHICLE,
)
from .entity import SecSpyBaseEntity

SENSORS = (
    SensorEntityDescription(key="detected_object", name="Detected object"),
    SensorEntityDescription(key="motion_recording", name="Motion recording"),
    SensorEntityDescription(key="continuous_recording", name="Continuous recording"),
    SensorEntityDescription(key="actions_enabled", name="Actions enabled"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    runtime = entry.runtime_data
    entities = [
        SecSpySensor(runtime.coordinator, cam_num, description)
        for cam_num in runtime.coordinator.data
        for description in SENSORS
    ]
    async_add_entities(entities)


class SecSpySensor(SecSpyBaseEntity, SensorEntity):
    """Read-only camera status sensor."""

    entity_description: SensorEntityDescription

    def __init__(self, coordinator, camera_number, description) -> None:
        super().__init__(coordinator, camera_number, key=description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | None:
        """Return sensor value."""
        cam = self.camera
        if cam is None:
            return None
        key = self.entity_description.key
        if key == "detected_object":
            return cam.event_object
        if key == "motion_recording":
            return "armed" if cam.armed_motion else "disarmed"
        if key == "continuous_recording":
            return "armed" if cam.armed_continuous else "disarmed"
        if key == "actions_enabled":
            return "armed" if cam.armed_actions else "disarmed"
        return None

    @property
    def extra_state_attributes(self) -> dict | None:
        """Scores for detected object sensor."""
        cam = self.camera
        if cam is None or self.entity_description.key != "detected_object":
            return None
        return {
            ATTR_EVENT_SCORE_HUMAN: cam.score_human,
            ATTR_EVENT_SCORE_VEHICLE: cam.score_vehicle,
            ATTR_EVENT_SCORE_ANIMAL: cam.score_animal,
        }
