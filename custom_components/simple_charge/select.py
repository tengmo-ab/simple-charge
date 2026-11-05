"""Mode: smart (price plan), force (charge now) or paused (hands off)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MODES, SET_MODE
from .coordinator import SimpleChargeConfigEntry
from .entity import SimpleChargeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimpleChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ModeSelect(entry.runtime_data, "mode")])


class ModeSelect(SimpleChargeEntity, SelectEntity):
    _attr_options = MODES
    _attr_icon = "mdi:auto-mode"

    @property
    def current_option(self) -> str | None:
        return self.settings.get(SET_MODE)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_setting(SET_MODE, option)
