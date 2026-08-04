"""Tests for the classify event entity firing behavior."""

from __future__ import annotations

from aiosecspy import Event, EventType

from custom_components.secspy.coordinator import SecSpyCoordinator
from custom_components.secspy.event import SecSpyClassifyEvent

from .conftest import FakeCamera, emit, make_client


def _make_entity(hass, entry, client, min_score=50) -> tuple:
    coordinator = SecSpyCoordinator(hass, entry, client, min_score=min_score)
    coordinator.async_set_updated_data(dict(client.cameras))
    entity = SecSpyClassifyEvent(coordinator, 1, min_score)
    entity.hass = hass
    # Writing state needs a platform/entity_id; we only care about the staged
    # event, so swap the write for a no-op.
    entity.async_write_ha_state = lambda: None
    client.events.add_listener(entity._handle_event)
    return coordinator, entity


async def test_top_scoring_class_wins(hass, mock_config_entry):
    """Only the top class at/above threshold fires; scores ride in attributes."""
    client = make_client({1: FakeCamera()})
    _, entity = _make_entity(hass, mock_config_entry, client)

    await emit(
        client,
        Event(
            event_type=EventType.CLASSIFY,
            camera_number=1,
            classify_human=90,
            classify_vehicle=70,
            classify_animal=-99,
        ),
    )
    assert entity._EventEntity__last_event_type == "human"
    assert entity._EventEntity__last_event_attributes == {
        "event_score_human": 90,
        "event_score_vehicle": 70,
        "event_score_animal": -99,
    }

    await emit(
        client,
        Event(
            event_type=EventType.CLASSIFY,
            camera_number=1,
            classify_human=60,
            classify_vehicle=99,
            classify_animal=-99,
        ),
    )
    assert entity._EventEntity__last_event_type == "vehicle"


async def test_below_threshold_does_not_fire(hass, mock_config_entry):
    """All scores below the minimum means no event."""
    client = make_client({1: FakeCamera()})
    _, entity = _make_entity(hass, mock_config_entry, client, min_score=50)

    await emit(
        client,
        Event(
            event_type=EventType.CLASSIFY,
            camera_number=1,
            classify_human=40,
            classify_vehicle=10,
            classify_animal=-99,
        ),
    )
    assert entity._EventEntity__last_event_type is None


async def test_other_camera_ignored(hass, mock_config_entry):
    """Events for another camera never fire this entity."""
    client = make_client({1: FakeCamera(), 2: FakeCamera()})
    _, entity = _make_entity(hass, mock_config_entry, client)

    await emit(
        client,
        Event(
            event_type=EventType.CLASSIFY,
            camera_number=2,
            classify_human=100,
            classify_vehicle=-99,
            classify_animal=-99,
        ),
    )
    assert entity._EventEntity__last_event_type is None
