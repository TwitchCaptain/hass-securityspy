"""Arm/disarm switches for SecuritySpy cameras."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiosecspy.exceptions import SecSpyError
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import async_refresh_camera_state
from .entity import SecSpyBaseEntity, async_add_camera_entities

if TYPE_CHECKING:
    from . import SecSpyConfigEntry
    from .coordinator import SecSpyCoordinator

SWITCHES = (
    SwitchEntityDescription(
        key="arm_motion",
        translation_key="arm_motion",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="arm_actions",
        translation_key="arm_actions",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="arm_continuous",
        translation_key="arm_continuous",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SecSpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    runtime = entry.runtime_data
    async_add_camera_entities(
        runtime.coordinator,
        async_add_entities,
        lambda number: [
            SecSpyArmSwitch(runtime.coordinator, number, description)
            for description in SWITCHES
        ],
    )


class SecSpyArmSwitch(SecSpyBaseEntity, SwitchEntity):
    """Switch to arm/disarm a camera mode."""

    entity_description: SwitchEntityDescription

    def __init__(
        self,
        coordinator: SecSpyCoordinator,
        camera_number: int,
        description: SwitchEntityDescription,
    ) -> None:
        """Bind the description to one camera."""
        super().__init__(coordinator, camera_number, key=description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return whether mode is armed."""
        cam = self.camera
        if cam is None:
            return False
        key = self.entity_description.key
        if key == "arm_motion":
            return cam.armed_motion
        if key == "arm_actions":
            return cam.armed_actions
        return cam.armed_continuous

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Arm mode."""
        await self._set_arm(arm=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disarm mode."""
        await self._set_arm(arm=False)

    async def _set_arm(self, *, arm: bool) -> None:
        client = self.coordinator.client
        key = self.entity_description.key
        try:
            if key == "arm_motion":
                await client.toggle_motion(self.camera_number, arm=arm)
            elif key == "arm_actions":
                await client.toggle_actions(self.camera_number, arm=arm)
            else:
                await client.toggle_continuous(self.camera_number, arm=arm)
            await async_refresh_camera_state(self.coordinator)
        except SecSpyError as err:
            raise HomeAssistantError(f"SecuritySpy command failed: {err}") from err
