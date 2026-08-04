"""Sensors for SecuritySpy cameras."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiosecspy import Camera
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_EVENT_SCORE_ANIMAL,
    ATTR_EVENT_SCORE_HUMAN,
    ATTR_EVENT_SCORE_VEHICLE,
)
from .entity import SecSpyBaseEntity, async_add_camera_entities

if TYPE_CHECKING:
    from . import SecSpyConfigEntry
    from .coordinator import SecSpyCoordinator


@dataclass(frozen=True, kw_only=True)
class SecSpySensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[Camera], str | None]


def _armed(value: bool) -> str:
    return "armed" if value else "disarmed"


SENSORS: tuple[SecSpySensorDescription, ...] = (
    SecSpySensorDescription(
        key="detected_object",
        translation_key="detected_object",
        device_class=SensorDeviceClass.ENUM,
        options=["human", "vehicle", "animal"],
        value_fn=lambda cam: cam.event_object,
    ),
    SecSpySensorDescription(
        key="motion_recording",
        translation_key="motion_recording",
        device_class=SensorDeviceClass.ENUM,
        options=["armed", "disarmed"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda cam: _armed(cam.armed_motion),
    ),
    SecSpySensorDescription(
        key="continuous_recording",
        translation_key="continuous_recording",
        device_class=SensorDeviceClass.ENUM,
        options=["armed", "disarmed"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda cam: _armed(cam.armed_continuous),
    ),
    SecSpySensorDescription(
        key="actions_enabled",
        translation_key="actions_enabled",
        device_class=SensorDeviceClass.ENUM,
        options=["armed", "disarmed"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda cam: _armed(cam.armed_actions),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SecSpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    runtime = entry.runtime_data
    async_add_camera_entities(
        runtime.coordinator,
        async_add_entities,
        lambda number: [
            SecSpySensor(runtime.coordinator, number, description)
            for description in SENSORS
        ],
    )


class SecSpySensor(SecSpyBaseEntity, SensorEntity):
    """Read-only camera status sensor."""

    entity_description: SecSpySensorDescription

    def __init__(
        self,
        coordinator: SecSpyCoordinator,
        camera_number: int,
        description: SecSpySensorDescription,
    ) -> None:
        """Bind the description to one camera."""
        super().__init__(coordinator, camera_number, key=description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | None:
        """Return sensor value."""
        cam = self.camera
        if cam is None:
            return None
        return self.entity_description.value_fn(cam)

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
