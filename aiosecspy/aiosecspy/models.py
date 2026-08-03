"""Data models for SecuritySpy systemInfo."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PTZCapabilities:
    """Decoded PTZ capability bitmask."""

    raw: int = 0
    has_pan_tilt: bool = False
    has_home: bool = False
    has_zoom: bool = False
    has_presets: bool = False
    has_speed: bool = False
    continuous: bool = False

    @classmethod
    def from_raw(cls, raw: int) -> PTZCapabilities:
        """Build from SecuritySpy capability integer."""
        from .const import (
            PTZ_CONTINUOUS,
            PTZ_HOME,
            PTZ_PAN_TILT,
            PTZ_PRESETS,
            PTZ_SPEED,
            PTZ_ZOOM,
        )

        return cls(
            raw=raw,
            has_pan_tilt=bool(raw & PTZ_PAN_TILT),
            has_home=bool(raw & PTZ_HOME),
            has_zoom=bool(raw & PTZ_ZOOM),
            has_presets=bool(raw & PTZ_PRESETS),
            has_speed=bool(raw & PTZ_SPEED),
            continuous=bool(raw & PTZ_CONTINUOUS),
        )


@dataclass
class Camera:
    """A SecuritySpy camera from ++systemInfo."""

    number: int
    name: str
    connected: bool = False
    width: int = 0
    height: int = 0
    mode_c: str = "disarmed"
    mode_m: str = "disarmed"
    mode_a: str = "disarmed"
    schedule_id_cc: int = 0
    schedule_id_mc: int = 0
    schedule_id_a: int = 0
    schedule_override_cc: int = 0
    schedule_override_mc: int = 0
    schedule_override_a: int = 0
    ptz: PTZCapabilities = field(default_factory=PTZCapabilities)
    preset_names: dict[int, str] = field(default_factory=dict)
    has_audio: bool = False
    md_enabled: bool = True
    # Runtime event state (updated by event stream)
    motion_active: bool = False
    event_object: str = "none"
    score_human: int = 0
    score_vehicle: int = 0
    score_animal: int = 0
    last_motion_time: str | None = None
    trigger_reasons: list[str] = field(default_factory=list)

    @property
    def armed_continuous(self) -> bool:
        """True if continuous capture is armed."""
        return self.mode_c.lower() == "armed"

    @property
    def armed_motion(self) -> bool:
        """True if motion capture is armed."""
        return self.mode_m.lower() == "armed"

    @property
    def armed_actions(self) -> bool:
        """True if actions are armed."""
        return self.mode_a.lower() == "armed"


@dataclass
class ServerInfo:
    """SecuritySpy server metadata from ++systemInfo."""

    name: str = "SecuritySpy"
    version: str = ""
    uuid: str = ""
    ip1: str = ""
    ip2: str = ""
    http_port: int = 8000
    https_port: int = 8001
    http_enabled: bool = True
    https_enabled: bool = False
    gmt_offset_seconds: int = 0
    camera_count: int = 0
    schedules: dict[int, str] = field(default_factory=dict)
    overrides: dict[int, str] = field(default_factory=dict)
    presets: dict[int, str] = field(default_factory=dict)
    cameras: dict[int, Camera] = field(default_factory=dict)

    @property
    def major_version(self) -> int:
        """Major version number (5 or 6, etc.)."""
        try:
            return int(self.version.split(".", maxsplit=1)[0])
        except (ValueError, IndexError):
            return 0
