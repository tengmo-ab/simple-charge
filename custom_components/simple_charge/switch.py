"""Switches: hand the charger over, use the forecast, ready-by deadline, Garo schedule."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_FORECAST_ENTITIES,
    CONF_GARO_SCHEDULE_ENTITY,
    SET_CHARGER_CONTROL,
    SET_DEADLINE_ENABLED,
    SET_GARO_SYNC,
    SET_USE_FORECAST,
)
from .coordinator import SimpleChargeConfigEntry, SimpleChargeCoordinator
from .entity import SimpleChargeEntity


@dataclass(frozen=True, kw_only=True)
class SimpleChargeSwitchDescription(SwitchEntityDescription):
    setting: str


CHARGER_CONTROL = SimpleChargeSwitchDescription(key="charger_control", setting=SET_CHARGER_CONTROL, icon="mdi:ev-plug-type2")
DEADLINE = SimpleChargeSwitchDescription(key="deadline_enabled", setting=SET_DEADLINE_ENABLED, icon="mdi:flag-checkered")
USE_FORECAST = SimpleChargeSwitchDescription(
    key="use_forecast",
    setting=SET_USE_FORECAST,
    icon="mdi:crystal-ball",
    entity_category=EntityCategory.CONFIG,
)
GARO_SYNC = SimpleChargeSwitchDescription(
    key="garo_schedule_sync",
    setting=SET_GARO_SYNC,
    icon="mdi:calendar-sync",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimpleChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    descriptions = [DEADLINE]
    if coordinator.charger.enabled:
        descriptions.append(CHARGER_CONTROL)
    if coordinator.options.get(CONF_FORECAST_ENTITIES):
        descriptions.append(USE_FORECAST)
    if coordinator.options.get(CONF_GARO_SCHEDULE_ENTITY):
        descriptions.append(GARO_SYNC)
    async_add_entities(SimpleChargeSwitch(coordinator, d) for d in descriptions)


class SimpleChargeSwitch(SimpleChargeEntity, SwitchEntity):
    entity_description: SimpleChargeSwitchDescription

    def __init__(self, coordinator: SimpleChargeCoordinator, description: SimpleChargeSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return bool(self.settings.get(self.entity_description.setting))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting(self.entity_description.setting, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting(self.entity_description.setting, False)
