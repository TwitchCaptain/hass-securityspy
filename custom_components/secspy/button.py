"""PTZ buttons for SecuritySpy cameras."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .aiosecspy import SecSpyClient
from .entity import SecSpyBaseEntity


@dataclass(frozen=True, kw_only=True)
class SecSpyButtonDescription(ButtonEntityDescription):
    """Button description with PTZ action."""

    press_fn: Callable[[SecSpyClient, int], Coroutine[Any, Any, None]]
    requires: str  # attribute on PTZCapabilities


BUTTONS: tuple[SecSpyButtonDescription, ...] = (
    SecSpyButtonDescription(
        key="ptz_left",
        name="PTZ left",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_left(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_right",
        name="PTZ right",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_right(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_up",
        name="PTZ up",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_up(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_down",
        name="PTZ down",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_down(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_zoom_in",
        name="PTZ zoom in",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_zoom(n, True),
        requires="has_zoom",
    ),
    SecSpyButtonDescription(
        key="ptz_zoom_out",
        name="PTZ zoom out",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_zoom(n, False),
        requires="has_zoom",
    ),
    SecSpyButtonDescription(
        key="ptz_home",
        name="PTZ home",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_home(n),
        requires="has_home",
    ),
    SecSpyButtonDescription(
        key="ptz_stop",
        name="PTZ stop",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_stop(n),
        requires="continuous",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PTZ buttons."""
    runtime = entry.runtime_data
    entities: list[ButtonEntity] = []
    for cam_num, cam in runtime.coordinator.data.items():
        for description in BUTTONS:
            if getattr(cam.ptz, description.requires, False):
                entities.append(
                    SecSpyPTZButton(runtime.coordinator, cam_num, description)
                )
        if cam.ptz.has_presets:
            for preset, name in cam.preset_names.items():
                entities.append(
                    SecSpyPTZPresetButton(
                        runtime.coordinator,
                        cam_num,
                        preset=preset,
                        preset_name=name or f"Preset {preset}",
                    )
                )
            # Also expose unnamed presets 1-8 if capabilities claim presets
            if not cam.preset_names:
                for preset in range(1, 9):
                    entities.append(
                        SecSpyPTZPresetButton(
                            runtime.coordinator,
                            cam_num,
                            preset=preset,
                            preset_name=f"Preset {preset}",
                        )
                    )
    async_add_entities(entities)


class SecSpyPTZButton(SecSpyBaseEntity, ButtonEntity):
    """PTZ movement button."""

    entity_description: SecSpyButtonDescription

    def __init__(self, coordinator, camera_number, description) -> None:
        super().__init__(coordinator, camera_number, key=description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Execute PTZ command."""
        await self.entity_description.press_fn(
            self.coordinator.client, self.camera_number
        )


class SecSpyPTZPresetButton(SecSpyBaseEntity, ButtonEntity):
    """PTZ preset recall button."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator, camera_number, *, preset: int, preset_name: str
    ) -> None:
        super().__init__(coordinator, camera_number, key=f"ptz_preset_{preset}")
        self._preset = preset
        self._attr_name = f"PTZ {preset_name}"

    async def async_press(self) -> None:
        """Go to preset."""
        await self.coordinator.client.ptz_preset(self.camera_number, self._preset)
