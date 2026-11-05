"""Selects: the mode (smart / force / paused) and how "ready by" treats prices."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEADLINE_MODES, MODES, SET_DEADLINE_MODE, SET_MODE
from .coordinator import SimpleChargeConfigEntry, SimpleChargeCoordinator
from .entity import SimpleChargeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimpleChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SettingSelect(coordinator, "mode", SET_MODE, MODES, "mdi:auto-mode"),
            SettingSelect(
                coordinator,
                "deadline_mode",
                SET_DEADLINE_MODE,
                DEADLINE_MODES,
                "mdi:flag-checkered",
                EntityCategory.CONFIG,
            ),
        ]
    )


class SettingSelect(SimpleChargeEntity, SelectEntity):
    def __init__(
        self,
        coordinator: SimpleChargeCoordinator,
        key: str,
        setting: str,
        options: list[str],
        icon: str,
        category: EntityCategory | None = None,
    ) -> None:
        super().__init__(coordinator, key)
        self._setting = setting
        self._attr_options = options
        self._attr_icon = icon
        self._attr_entity_category = category

    @property
    def current_option(self) -> str | None:
        return self.settings.get(self._setting)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_setting(self._setting, option)
