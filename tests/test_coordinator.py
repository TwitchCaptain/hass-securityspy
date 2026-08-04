"""Tests for the secspy push coordinator's event handling."""

from __future__ import annotations

from aiosecspy import Event, EventType

from custom_components.secspy.coordinator import SecSpyCoordinator

from .conftest import emit, make_camera, make_client


def _make_coordinator(hass, entry, client) -> SecSpyCoordinator:
    coordinator = SecSpyCoordinator(hass, entry, client)
    coordinator.async_set_updated_data(dict(client.cameras))
    coordinator._unsub_stream = client.events.add_listener(coordinator._on_event)
    return coordinator


async def test_null_keepalive_does_not_update_or_fire(hass, mock_config_entry):
    """NULL keepalives must not touch coordinator state or the event bus."""
    client = make_client()
    coordinator = _make_coordinator(hass, mock_config_entry, client)

    updates = 0
    bus_events = []

    def _listener():
        nonlocal updates
        updates += 1

    coordinator.async_add_listener(_listener)
    remove = hass.bus.async_listen("secspy_event", bus_events.append)

    await emit(client, Event(event_type=EventType.NULL, camera_number=None))
    assert updates == 0
    assert bus_events == []
    remove()


async def test_motion_events_update_camera_state(hass, mock_config_entry):
    """TRIGGER_M turns motion on, MOTION_END turns it off (via the library)."""
    client = make_client({1: make_camera(1)})
    coordinator = _make_coordinator(hass, mock_config_entry, client)

    await emit(client, Event(event_type=EventType.TRIGGER_M, camera_number=1))
    assert coordinator.data[1].motion_active is True

    await emit(client, Event(event_type=EventType.MOTION_END, camera_number=1))
    assert coordinator.data[1].motion_active is False


async def test_classify_updates_scores_and_top_object(hass, mock_config_entry):
    """CLASSIFY stores raw scores and picks the top class for detected_object."""
    client = make_client({2: make_camera(2)})
    coordinator = _make_coordinator(hass, mock_config_entry, client)

    await emit(
        client,
        Event(
            event_type=EventType.CLASSIFY,
            camera_number=2,
            classify_human=80,
            classify_vehicle=95,
            classify_animal=-99,
        ),
    )
    cam = coordinator.data[2]
    assert cam.score_human == 80
    assert cam.score_vehicle == 95
    assert cam.event_object == "vehicle"


async def test_classify_absent_scores_clear_previous_values(hass, mock_config_entry):
    """A class absent from a later CLASSIFY event must not keep a stale score."""
    client = make_client({2: make_camera(2)})
    coordinator = _make_coordinator(hass, mock_config_entry, client)

    await emit(
        client,
        Event(
            event_type=EventType.CLASSIFY,
            camera_number=2,
            classify_human=10,
            classify_vehicle=95,
            classify_animal=-99,
        ),
    )
    await emit(
        client,
        Event(
            event_type=EventType.CLASSIFY,
            camera_number=2,
            classify_human=85,
            classify_vehicle=-99,
            classify_animal=-99,
        ),
    )
    cam = coordinator.data[2]
    assert cam.score_human == 85
    assert cam.score_vehicle == -99
    assert cam.event_object == "human"


async def test_arm_events_flip_switch_state(hass, mock_config_entry):
    """ARM/DISARM events land in the coordinator snapshot."""
    client = make_client({1: make_camera(1, mode_m="armed")})
    coordinator = _make_coordinator(hass, mock_config_entry, client)

    await emit(client, Event(event_type=EventType.DISARM_M, camera_number=1))
    assert coordinator.data[1].armed_motion is False

    await emit(client, Event(event_type=EventType.ARM_M, camera_number=1))
    assert coordinator.data[1].armed_motion is True


async def test_connect_disconnect_track_stream_health(hass, mock_config_entry):
    """CONNECTED/DISCONNECTED flip stream_connected for the diagnostic sensor."""
    client = make_client({0: make_camera()})
    coordinator = _make_coordinator(hass, mock_config_entry, client)
    assert coordinator.stream_connected is False

    await emit(client, Event(event_type=EventType.CONNECTED))
    assert coordinator.stream_connected is True

    await emit(client, Event(event_type=EventType.DISCONNECTED))
    assert coordinator.stream_connected is False


async def test_authfail_starts_reauth_once(hass, mock_config_entry, monkeypatch):
    """AUTHFAIL starts the reauth flow exactly once."""
    client = make_client()
    _make_coordinator(hass, mock_config_entry, client)

    calls = []
    monkeypatch.setattr(
        mock_config_entry,
        "async_start_reauth",
        lambda hass: calls.append(hass),
        raising=False,
    )

    await emit(
        client,
        Event(event_type=EventType.AUTHFAIL),
        Event(event_type=EventType.AUTHFAIL),
    )
    assert len(calls) == 1


async def test_lifecycle_events_do_not_fire_bus(hass, mock_config_entry, monkeypatch):
    """CONNECTED/DISCONNECTED/AUTHFAIL stay off the recorded event bus."""
    client = make_client()
    _make_coordinator(hass, mock_config_entry, client)
    # Keep AUTHFAIL from launching a real reauth flow against the integration
    # loader (this test only cares about bus traffic).
    monkeypatch.setattr(
        mock_config_entry, "async_start_reauth", lambda hass: None, raising=False
    )

    bus_events = []
    remove = hass.bus.async_listen("secspy_event", bus_events.append)

    await emit(
        client,
        Event(event_type=EventType.CONNECTED),
        Event(event_type=EventType.DISCONNECTED),
        Event(event_type=EventType.AUTHFAIL),
    )
    await hass.async_block_till_done()
    assert bus_events == []
    remove()


async def test_real_events_fire_bus_with_attribute_keys(hass, mock_config_entry):
    """Wire events fire secspy_event with keys matching entity attributes."""
    client = make_client({3: make_camera(3, "Garage")})
    _make_coordinator(hass, mock_config_entry, client)

    bus_events = []
    remove = hass.bus.async_listen("secspy_event", bus_events.append)

    await emit(
        client,
        Event(
            event_type=EventType.TRIGGER_M,
            camera_number=3,
            reason_names=["Motion Detected"],
            classify_human=88,
        ),
    )
    await hass.async_block_till_done()
    assert len(bus_events) == 1
    data = bus_events[0].data
    assert data["type"] == "TRIGGER_M"
    assert data["camera_number"] == 3
    assert data["camera_name"] == "Garage"
    assert data["trigger_reasons"] == ["Motion Detected"]
    assert data["event_score_human"] == 88
    remove()
