"""Adjustable numbers: how long to charge and how expensive is too expensive."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_BATTERY_KWH,
    CONF_SOC_ENTITY,
    SET_DURATION_HOURS,
    SET_MAX_PRICE,
    SET_RELATIVE_LIMIT,
    SET_TARGET_SOC,
)
from .coordinator import SimpleChargeConfigEntry, SimpleChargeCoordinator
from .entity import SimpleChargeEntity


@dataclass(frozen=True, kw_only=True)
class SimpleChargeNumberDescription(NumberEntityDescription):
    setting: str
    price_unit: bool = False


NUMBERS: tuple[SimpleChargeNumberDescription, ...] = (
    SimpleChargeNumberDescription(
        key="duration",
        setting=SET_DURATION_HOURS,
        icon="mdi:timer-outline",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        native_min_value=0,
        native_max_value=24,
        native_step=0.25,
        mode=NumberMode.BOX,
    ),
    SimpleChargeNumberDescription(
        key="max_price",
        setting=SET_MAX_PRICE,
        icon="mdi:cash-lock",
        native_min_value=0,
        native_max_value=100000,
        native_step=0.01,
        mode=NumberMode.BOX,
        price_unit=True,
    ),
    SimpleChargeNumberDescription(
        key="relative_limit",
        setting=SET_RELATIVE_LIMIT,
        icon="mdi:percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=200,
        native_step=1,
        mode=NumberMode.BOX,
    ),
)

TARGET_SOC = SimpleChargeNumberDescription(
    key="target_soc",
    setting=SET_TARGET_SOC,
    icon="mdi:battery-charging-80",
    device_class=NumberDeviceClass.BATTERY,
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=10,
    native_max_value=100,
    native_step=1,
    mode=NumberMode.SLIDER,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimpleChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    descriptions = list(NUMBERS)
    if coordinator.options.get(CONF_SOC_ENTITY) and coordinator.options.get(CONF_BATTERY_KWH):
        descriptions.append(TARGET_SOC)
    async_add_entities(SimpleChargeNumber(coordinator, d) for d in descriptions)


class SimpleChargeNumber(SimpleChargeEntity, NumberEntity):
    entity_description: SimpleChargeNumberDescription

    def __init__(self, coordinator: SimpleChargeCoordinator, description: SimpleChargeNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        value = self.settings.get(self.entity_description.setting)
        return float(value) if value is not None else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.price_unit:
            return self.coordinator.unit
        return self.entity_description.native_unit_of_measurement

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_setting(self.entity_description.setting, value)
