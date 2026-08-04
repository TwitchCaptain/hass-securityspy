"""PTZ buttons for SecuritySpy cameras."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aiosecspy import SecSpyClient
from aiosecspy.exceptions import SecSpyError
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SecSpyBaseEntity, async_add_camera_entities

if TYPE_CHECKING:
    from . import SecSpyConfigEntry
    from .coordinator import SecSpyCoordinator


@dataclass(frozen=True, kw_only=True)
class SecSpyButtonDescription(ButtonEntityDescription):
    """Button description with PTZ action."""

    press_fn: Callable[[SecSpyClient, int], Coroutine[Any, Any, None]]
    requires: str  # attribute on PTZCapabilities


BUTTONS: tuple[SecSpyButtonDescription, ...] = (
    SecSpyButtonDescription(
        key="ptz_left",
        translation_key="ptz_left",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_left(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_right",
        translation_key="ptz_right",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_right(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_up",
        translation_key="ptz_up",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_up(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_down",
        translation_key="ptz_down",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_down(n),
        requires="has_pan_tilt",
    ),
    SecSpyButtonDescription(
        key="ptz_zoom_in",
        translation_key="ptz_zoom_in",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_zoom(n, zoom_in=True),
        requires="has_zoom",
    ),
    SecSpyButtonDescription(
        key="ptz_zoom_out",
        translation_key="ptz_zoom_out",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_zoom(n, zoom_in=False),
        requires="has_zoom",
    ),
    SecSpyButtonDescription(
        key="ptz_home",
        translation_key="ptz_home",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_home(n),
        requires="has_home",
    ),
    SecSpyButtonDescription(
        key="ptz_stop",
        translation_key="ptz_stop",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c, n: c.ptz_stop(n),
        requires="continuous",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SecSpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PTZ buttons."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator

    def _factory(number: int) -> list[Entity]:
        cam = coordinator.data.get(number)
        if cam is None:
            return []
        entities: list[Entity] = [
            SecSpyPTZButton(coordinator, number, description)
            for description in BUTTONS
            if getattr(cam.ptz, description.requires, False)
        ]
        if cam.ptz.has_presets:
            # Named presets from ++systemInfo, or the full 1-8 range when the
            # capability is claimed but no names are configured.
            presets = cam.preset_names or {i: f"Preset {i}" for i in range(1, 9)}
            entities.extend(
                SecSpyPTZPresetButton(
                    coordinator,
                    number,
                    preset=preset,
                    preset_name=name or f"Preset {preset}",
                )
                for preset, name in presets.items()
            )
        return entities

    async_add_camera_entities(coordinator, async_add_entities, _factory)


class SecSpyPTZButton(SecSpyBaseEntity, ButtonEntity):
    """PTZ movement button."""

    entity_description: SecSpyButtonDescription

    def __init__(
        self,
        coordinator: SecSpyCoordinator,
        camera_number: int,
        description: SecSpyButtonDescription,
    ) -> None:
        """Bind the description to one camera."""
        super().__init__(coordinator, camera_number, key=description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Execute PTZ command."""
        try:
            await self.entity_description.press_fn(
                self.coordinator.client, self.camera_number
            )
        except SecSpyError as err:
            raise HomeAssistantError(f"PTZ command failed: {err}") from err


class SecSpyPTZPresetButton(SecSpyBaseEntity, ButtonEntity):
    """PTZ preset recall button."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: SecSpyCoordinator,
        camera_number: int,
        *,
        preset: int,
        preset_name: str,
    ) -> None:
        """Bind one preset number to a button."""
        super().__init__(coordinator, camera_number, key=f"ptz_preset_{preset}")
        self._preset = preset
        self._attr_name = f"PTZ {preset_name}"

    async def async_press(self) -> None:
        """Go to preset."""
        try:
            await self.coordinator.client.ptz_preset(self.camera_number, self._preset)
        except SecSpyError as err:
            raise HomeAssistantError(f"PTZ preset failed: {err}") from err
