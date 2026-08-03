"""Parse ++systemInfo XML (SecuritySpy v5 and v6)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .models import Camera, PTZCapabilities, ServerInfo


def _text(node: ET.Element | None, *tags: str, default: str = "") -> str:
    if node is None:
        return default
    for tag in tags:
        el = node.find(tag)
        if el is not None and el.text is not None:
            return el.text
    return default


def _int(node: ET.Element | None, *tags: str, default: int = 0) -> int:
    raw = _text(node, *tags, default="")
    try:
        return int(float(raw)) if raw else default
    except ValueError:
        return default


def _boolish(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "armed"}


def _parse_named_list(root: ET.Element, *paths: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for path in paths:
        for node in root.findall(path):
            sid = _text(node, "id")
            name = _text(node, "name")
            if sid.isdigit():
                out[int(sid)] = name
    return out


def _parse_camera(node: ET.Element) -> Camera:
    number = _int(node, "number", "cameraNum")
    name = _text(node, "name") or f"Camera {number}"
    connected_raw = _text(node, "connected", default="false")
    ptz_raw = _int(node, "ptz-features", "ptzcapabilities")
    presets: dict[int, str] = {}
    for i in range(1, 9):
        pname = _text(node, f"preset-name-{i}")
        if pname:
            presets[i] = pname

    return Camera(
        number=number,
        name=name,
        connected=_boolish(connected_raw),
        width=_int(node, "video-width", "width"),
        height=_int(node, "video-height", "height"),
        mode_c=_text(node, "cc-mode", "mode-c", default="disarmed").lower(),
        mode_m=_text(node, "mc-mode", "mode-m", default="disarmed").lower(),
        mode_a=_text(node, "a-mode", "mode-a", default="disarmed").lower(),
        schedule_id_cc=_int(node, "cc-schedule-id", "schedule-id-cc"),
        schedule_id_mc=_int(node, "mc-schedule-id", "schedule-id-mc"),
        schedule_id_a=_int(node, "a-schedule-id", "schedule-id-a"),
        schedule_override_cc=_int(node, "cc-schedule-override", "schedule-override-cc"),
        schedule_override_mc=_int(node, "mc-schedule-override", "schedule-override-mc"),
        schedule_override_a=_int(node, "a-schedule-override", "schedule-override-a"),
        ptz=PTZCapabilities.from_raw(ptz_raw),
        preset_names=presets,
        has_audio=_boolish(_text(node, "has-audio", "hasaudio", default="false")),
        md_enabled=_boolish(_text(node, "md_enabled", default="yes")),
    )


def parse_system_info(xml_text: str) -> ServerInfo:
    """Parse SecuritySpy ++systemInfo XML into ServerInfo."""
    root = ET.fromstring(xml_text)
    server = root.find("server")
    info = ServerInfo(
        name=_text(server, "server-name", "name", default="SecuritySpy")
        or "SecuritySpy",
        version=_text(server, "version"),
        uuid=_text(server, "uuid"),
        ip1=_text(server, "ip1"),
        ip2=_text(server, "ip2"),
        http_port=_int(server, "http-port", default=8000),
        https_port=_int(server, "https-port", default=8001),
        http_enabled=_boolish(_text(server, "http-enabled", default="yes")),
        https_enabled=_boolish(_text(server, "https-enabled", default="no")),
        gmt_offset_seconds=_int(server, "seconds-from-gmt"),
        camera_count=_int(server, "camera-count"),
        schedules=_parse_named_list(
            root, ".//schedule-list/schedule", ".//schedulelist/schedule"
        ),
        overrides=_parse_named_list(
            root,
            ".//schedule-override-list/schedule-override",
            ".//scheduleoverridelist/scheduleoverride",
        ),
        presets=_parse_named_list(
            root,
            ".//schedule-preset-list/schedule-preset",
            ".//schedulepresetlist/schedulepreset",
        ),
    )

    cam_nodes = root.findall(".//camera-list/camera") or root.findall(
        ".//cameralist/camera"
    )
    for node in cam_nodes:
        cam = _parse_camera(node)
        info.cameras[cam.number] = cam
    if not info.camera_count:
        info.camera_count = len(info.cameras)
    return info
