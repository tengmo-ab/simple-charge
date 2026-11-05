"""Date/time settings: ready-by deadline and a force-charge window."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SET_DEADLINE, SET_WINDOW_END, SET_WINDOW_START
from .coordinator import SimpleChargeConfigEntry, SimpleChargeCoordinator
from .entity import SimpleChargeEntity

ITEMS = (
    ("deadline", SET_DEADLINE, "mdi:clock-end"),
    ("force_window_start", SET_WINDOW_START, "mdi:clock-start"),
    ("force_window_end", SET_WINDOW_END, "mdi:clock-end"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimpleChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SimpleChargeDateTime(coordinator, key, setting, icon) for key, setting, icon in ITEMS)


class SimpleChargeDateTime(SimpleChargeEntity, DateTimeEntity):
    def __init__(self, coordinator: SimpleChargeCoordinator, key: str, setting: str, icon: str) -> None:
        super().__init__(coordinator, key)
        self._setting = setting
        self._attr_icon = icon

    @property
    def native_value(self) -> datetime | None:
        return self.settings.get(self._setting)

    async def async_set_value(self, value: datetime) -> None:
        await self.coordinator.async_set_setting(self._setting, value)
