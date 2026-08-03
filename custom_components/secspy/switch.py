"""Arm/disarm switches for SecuritySpy cameras."""

from __future__ import annotations

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SecSpyBaseEntity
from .coordinator import preserve_runtime_camera_state

SWITCHES = (
    SwitchEntityDescription(
        key="arm_motion",
        name="Arm motion",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="arm_actions",
        name="Arm actions",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="arm_continuous",
        name="Arm continuous",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    runtime = entry.runtime_data
    entities = [
        SecSpyArmSwitch(runtime.coordinator, cam_num, description)
        for cam_num in runtime.coordinator.data
        for description in SWITCHES
    ]
    async_add_entities(entities)


class SecSpyArmSwitch(SecSpyBaseEntity, SwitchEntity):
    """Switch to arm/disarm a camera mode."""

    entity_description: SwitchEntityDescription

    def __init__(self, coordinator, camera_number, description) -> None:
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

    async def async_turn_on(self, **kwargs) -> None:
        """Arm mode."""
        await self._set_arm(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disarm mode."""
        await self._set_arm(False)

    async def _set_arm(self, arm: bool) -> None:
        client = self.coordinator.client
        key = self.entity_description.key
        if key == "arm_motion":
            await client.toggle_motion(self.camera_number, arm)
        elif key == "arm_actions":
            await client.toggle_actions(self.camera_number, arm)
        else:
            await client.toggle_continuous(self.camera_number, arm)
        await client.refresh()
        self.coordinator.async_set_updated_data(
            preserve_runtime_camera_state(
                dict(self.coordinator.data or {}),
                dict(client.cameras),
            )
        )
        self.async_write_ha_state()
