"""Tests for systemInfo parsing and event line parsing."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiosecspy.const import EventType, TriggerReason
from aiosecspy.events import parse_event_line
from aiosecspy.systeminfo import parse_system_info

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_system_info_v6() -> None:
    xml = (FIXTURES / "systemInfo-v6.xml").read_text()
    info = parse_system_info(xml)
    assert info.version == "6.20"
    assert info.uuid == "EXAMPLEUUID000000001"
    assert info.name == "Example Server"
    assert 3 in info.cameras
    door = info.cameras[3]
    assert door.name == "Door"
    assert door.connected is True
    assert door.armed_motion is True
    assert door.armed_actions is True
    assert door.ptz.has_pan_tilt is True
    assert info.schedules[1] == "Armed 24/7"
    assert info.overrides[0] == "No Override"


def test_parse_system_info_v5() -> None:
    xml = (FIXTURES / "systemInfo-v5.xml").read_text()
    info = parse_system_info(xml)
    assert info.version.startswith("5.")
    assert 1 in info.cameras
    porch = info.cameras[1]
    assert porch.name == "Porch"
    assert porch.armed_continuous is True
    assert porch.width == 2304


@pytest.mark.parametrize(
    ("line", "etype", "cam"),
    [
        ("20190927092026 3 3 CLASSIFY HUMAN 99", EventType.CLASSIFY, 3),
        ("20190927092026 4 3 TRIGGER_M 9", EventType.TRIGGER_M, 3),
        ("20190927092040 5 X NULL", EventType.NULL, None),
        ("20190927092055 7 3 DISARM_M", EventType.DISARM_M, 3),
        ("20190927092056 8 3 OFFLINE", EventType.OFFLINE, 3),
        ("20190927092036 5 3 MOTION_END", EventType.MOTION_END, 3),
    ],
)
def test_parse_event_line(line: str, etype: EventType, cam: int | None) -> None:
    event = parse_event_line(line)
    assert event.event_type == etype
    assert event.camera_number == cam


def test_parse_classify_scores() -> None:
    event = parse_event_line(
        "20190927092036 5 3 CLASSIFY HUMAN 5 VEHICLE 95 ANIMAL 12"
    )
    assert event.event_type == EventType.CLASSIFY
    assert event.classify_human == 5
    assert event.classify_vehicle == 95
    assert event.classify_animal == 12


def test_parse_trigger_reasons() -> None:
    # bitmask 9 = motion(1) + camera_event(8)
    event = parse_event_line("20190927092026 4 3 TRIGGER_M 9")
    assert TriggerReason.MOTION in event.reasons
    assert TriggerReason.CAMERA_EVENT in event.reasons
    assert "Motion Detected" in event.reason_names


def test_parse_trigger_reasons_v5_animal_bit() -> None:
    # On v5, bit 512 is Animal (not HomeKit).
    event = parse_event_line(
        "20190927092026 4 3 TRIGGER_M 512", major_version=5
    )
    assert TriggerReason.ANIMAL in event.reasons
    assert TriggerReason.HOMEKIT not in event.reasons
    assert "Animal Detected" in event.reason_names


def test_parse_trigger_reasons_v6_homekit_bit() -> None:
    event = parse_event_line(
        "20190927092026 4 3 TRIGGER_M 512", major_version=6
    )
    assert TriggerReason.HOMEKIT in event.reasons
    assert "HomeKit Event" in event.reason_names
