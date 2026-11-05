"""The main output: should the car charge right now?"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SimpleChargeConfigEntry
from .entity import SimpleChargeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimpleChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ChargeNowBinarySensor(entry.runtime_data, "charge_now")])


class ChargeNowBinarySensor(SimpleChargeEntity, BinarySensorEntity):
    """On while the plan says charge. Other automations can use it as a request."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.charge_now)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan = self.coordinator.data
        if plan is None:
            return {}
        nxt = plan.next_start(dt_util.now())
        return {
            "reason": str(plan.reason),
            "next_start": nxt.isoformat() if nxt else None,
        }
