# SecuritySpy for Home Assistant

Custom Home Assistant integration that talks to [SecuritySpy](https://www.bensoftware.com/securityspy/) (v5 and v6) over its local web API.

- Watches the live `++eventStream` for motion, AI classify (human/vehicle/animal), arm/disarm, and online/offline.
- Exposes cameras, switches, sensors, event entities, and PTZ buttons.
- Provides services to arm modes, set schedules/overrides, trigger motion, and download the latest motion clip.

Domain: **`secspy`** (avoids clashing with older HACS `securityspy` integrations).

## Install (HACS)

1. Add this repository as a custom repository (Integration) in HACS, or install once published.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **SecuritySpy**.
4. Enter host, port, username, password. Enable HTTPS / SSL verify as needed.

Requires SecuritySpy **5.3.4+** (6.x supported). Use an **admin** web user.

## What you get

Per camera device:

| Platform | Entities |
|---|---|
| `binary_sensor` | Motion (on until `MOTION_END`), Online |
| `event` | Classification (`human` / `vehicle` / `animal`), Trigger (`motion` / `action`) |
| `sensor` | Detected object + scores, armed state for motion/continuous/actions |
| `switch` | Arm motion, Arm actions, Arm continuous |
| `camera` | Snapshot + RTSP (or MJPEG if RTSP disabled in options) |
| `button` | PTZ controls / presets when the camera supports them |

Also fires bus events: `secspy_event` with `type`, `camera_number`, scores, and reasons.

## Automations

**Sticky motion binary sensor**

```yaml
automation:
  - alias: Porch motion lights
    trigger:
      - platform: state
        entity_id: binary_sensor.porch_motion
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.porch
```

**AI human classify (event entity)**

```yaml
automation:
  - alias: Human at door
    trigger:
      - platform: state
        entity_id: event.door_classification
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.event_type == 'human' }}"
    action:
      - service: notify.mobile_app
        data:
          message: "Human at the door"
```

**Bus event (power users)**

```yaml
automation:
  - alias: Any SecuritySpy trigger
    trigger:
      - platform: event
        event_type: secspy_event
        event_data:
          type: TRIGGER_M
    action:
      - service: persistent_notification.create
        data:
          message: "Motion on camera {{ trigger.event.data.camera_number }}"
```

## Services

| Service | Purpose |
|---|---|
| `secspy.set_arm_mode` | Arm/disarm `continuous` / `on_motion` / `action` |
| `secspy.trigger_motion` | `++triggermd` |
| `secspy.set_schedule` | Mode `C`/`M`/`A`/`X` + schedule id |
| `secspy.set_schedule_override` | Mode + override id |
| `secspy.enable_schedule_preset` | Server-wide preset |
| `secspy.download_latest_motion_recording` | Save latest motion clip to a HA path |

Pass any entity belonging to the camera (for example the camera entity or motion binary sensor) as `entity_id`.

## Options

- **Disable RTSP** — use MJPEG (`++video`) for the camera stream instead of RTSP.
- **Minimum AI classify score** — threshold for classify event entity firings (default 50).

## Architecture

```text
aiosecspy/                 # publishable async Python client (PyPI)
custom_components/secspy/  # HACS integration (vendors aiosecspy for install)
```

The integration vendors `aiosecspy` under `custom_components/secspy/aiosecspy` so HACS works without a PyPI release. After editing the library:

```bash
python scripts/sync_aiosecspy.py
```

## Manual validation checklist (SS5 / SS6)

- [ ] Config flow connects (HTTP and HTTPS).
- [ ] Cameras appear with correct names; online binary sensor tracks ONLINE/OFFLINE.
- [ ] Motion binary sensor turns on for `TRIGGER_M` and off for `MOTION_END`.
- [ ] Classify event entity fires with human/vehicle/animal scores.
- [ ] Arm switches toggle modes; continuous falls back to schedule when soft toggle 404s.
- [ ] `set_schedule` / `set_schedule_override` / `enable_schedule_preset` succeed.
- [ ] Camera snapshot works; RTSP or MJPEG stream loads.
- [ ] PTZ buttons appear only when capabilities are present.
- [ ] `download_latest_motion_recording` writes a file.

## Development

```bash
pip install -e "./aiosecspy[dev]"
python scripts/sync_aiosecspy.py
pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
