"""Event entities for SecuritySpy classify/trigger events."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from aiosecspy import Event, EventType
from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_EVENT_SCORE_ANIMAL,
    ATTR_EVENT_SCORE_HUMAN,
    ATTR_EVENT_SCORE_VEHICLE,
    ATTR_TRIGGER_REASONS,
)
from .entity import SecSpyBaseEntity, async_add_camera_entities

if TYPE_CHECKING:
    from . import SecSpyConfigEntry
    from .coordinator import SecSpyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SecSpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up event entities."""
    runtime = entry.runtime_data

    def _factory(number: int) -> list[Entity]:
        return [
            SecSpyClassifyEvent(runtime.coordinator, number, runtime.min_score),
            SecSpyTriggerEvent(runtime.coordinator, number),
        ]

    async_add_camera_entities(runtime.coordinator, async_add_entities, _factory)


class SecSpyClassifyEvent(SecSpyBaseEntity, EventEntity):
    """Fires when CLASSIFY events arrive with scores above threshold."""

    _attr_event_types: ClassVar[list[str]] = ["human", "vehicle", "animal"]
    _attr_translation_key = "classify"
    _attr_device_class = EventDeviceClass.MOTION

    def __init__(
        self, coordinator: SecSpyCoordinator, camera_number: int, min_score: int
    ) -> None:
        """Bind the classify listener to one camera."""
        super().__init__(coordinator, camera_number, key="classify")
        self._min_score = min_score
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to the client's event stream."""
        await super().async_added_to_hass()
        self._unsub = self.coordinator.client.events.add_listener(self._handle_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from the client's event stream."""
        if self._unsub:
            self._unsub()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_event(self, event: Event) -> None:
        if event.event_type is not EventType.CLASSIFY:
            return
        if event.camera_number != self.camera_number:
            return
        # _trigger_event only stages one event until async_write_ha_state(),
        # so fire a single event for the top-scoring class at or above the
        # threshold. All class scores ride along in the event attributes.
        scores = {
            "human": event.classify_human,
            "vehicle": event.classify_vehicle,
            "animal": event.classify_animal,
        }
        top_class, top_score = max(scores.items(), key=lambda item: item[1])
        if top_score < self._min_score:
            return
        self._trigger_event(
            top_class,
            {
                ATTR_EVENT_SCORE_HUMAN: event.classify_human,
                ATTR_EVENT_SCORE_VEHICLE: event.classify_vehicle,
                ATTR_EVENT_SCORE_ANIMAL: event.classify_animal,
            },
        )
        self.async_write_ha_state()


class SecSpyTriggerEvent(SecSpyBaseEntity, EventEntity):
    """Fires on TRIGGER_M / TRIGGER_A."""

    _attr_event_types: ClassVar[list[str]] = ["motion", "action"]
    _attr_translation_key = "trigger"
    _attr_device_class = EventDeviceClass.MOTION

    def __init__(self, coordinator: SecSpyCoordinator, camera_number: int) -> None:
        """Bind the trigger listener to one camera."""
        super().__init__(coordinator, camera_number, key="trigger")
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to the client's event stream."""
        await super().async_added_to_hass()
        self._unsub = self.coordinator.client.events.add_listener(self._handle_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from the client's event stream."""
        if self._unsub:
            self._unsub()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_event(self, event: Event) -> None:
        if event.camera_number != self.camera_number:
            return
        if event.event_type is EventType.TRIGGER_M:
            event_name = "motion"
        elif event.event_type is EventType.TRIGGER_A:
            event_name = "action"
        else:
            return
        self._trigger_event(
            event_name,
            {ATTR_TRIGGER_REASONS: event.reason_names, "msg": event.msg},
        )
        self.async_write_ha_state()
