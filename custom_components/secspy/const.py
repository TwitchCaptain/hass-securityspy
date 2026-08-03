"""Constants for the secspy Home Assistant integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "secspy"
DEFAULT_NAME: Final = "SecuritySpy"
DEFAULT_PORT: Final = 8000
DEFAULT_MIN_SCORE: Final = 50
DEFAULT_BRAND: Final = "Ben Software"
MIN_SECSPY_VERSION: Final = "5.3.4"

CONF_USE_SSL: Final = "use_ssl"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_DISABLE_RTSP: Final = "disable_rtsp"
CONF_MIN_SCORE: Final = "min_event_score"

ATTR_CAMERA_NUMBER: Final = "camera_number"
ATTR_EVENT_OBJECT: Final = "event_object"
ATTR_EVENT_SCORE_HUMAN: Final = "event_score_human"
ATTR_EVENT_SCORE_VEHICLE: Final = "event_score_vehicle"
ATTR_EVENT_SCORE_ANIMAL: Final = "event_score_animal"
ATTR_TRIGGER_REASONS: Final = "trigger_reasons"
ATTR_LAST_TRIP_TIME: Final = "last_trip_time"
ATTR_PRESET_ID: Final = "preset_id"
ATTR_SCHEDULE_ID: Final = "schedule_id"
ATTR_OVERRIDE_ID: Final = "override_id"
ATTR_MODE: Final = "mode"
ATTR_ENABLED: Final = "enabled"

SERVICE_SET_ARM_MODE: Final = "set_arm_mode"
SERVICE_TRIGGER_MOTION: Final = "trigger_motion"
SERVICE_SET_SCHEDULE: Final = "set_schedule"
SERVICE_SET_SCHEDULE_OVERRIDE: Final = "set_schedule_override"
SERVICE_ENABLE_SCHEDULE_PRESET: Final = "enable_schedule_preset"
SERVICE_DOWNLOAD_LATEST_MOTION_RECORDING: Final = "download_latest_motion_recording"

MODE_CONTINUOUS: Final = "continuous"
MODE_MOTION: Final = "on_motion"
MODE_ACTION: Final = "action"
VALID_ARM_MODES: Final = [MODE_CONTINUOUS, MODE_MOTION, MODE_ACTION]

PLATFORMS: Final = [
    "binary_sensor",
    "button",
    "camera",
    "event",
    "sensor",
    "switch",
]

EVENT_BUS_TYPE: Final = "secspy_event"
