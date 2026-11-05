"""Sensors that explain the plan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .charger import (
    STATUS_FAILED,
    STATUS_IDLE,
    STATUS_OK,
    STATUS_PENDING,
    STATUS_UNAVAILABLE,
)
from .coordinator import SimpleChargeConfigEntry, SimpleChargeCoordinator
from .entity import SimpleChargeEntity
from .planner import PriceSlot, Reason, merge_ranges
from .prices import average


def format_ranges(ranges: list[tuple[datetime, datetime]]) -> str:
    """'5/11 23:15–00:00, 6/11 02:00–03:30' in local time."""
    parts: list[str] = []
    for start, end in ranges:
        start, end = dt_util.as_local(start), dt_util.as_local(end)
        parts.append(f"{start.day}/{start.month} {start:%H:%M}–{end:%H:%M}")
    text = ", ".join(parts)
    return text if len(text) <= 255 else text[:252] + "..."


def slot_list(slots: list[PriceSlot]) -> list[dict[str, Any]]:
    return [{"start": s.start.isoformat(), "end": s.end.isoformat(), "price": round(s.price, 3)} for s in slots]


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


@dataclass(frozen=True, kw_only=True)
class SimpleChargeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SimpleChargeCoordinator], Any]
    attrs_fn: Callable[[SimpleChargeCoordinator], dict[str, Any]] | None = None
    price_unit: bool = False


def _plan_value(c: SimpleChargeCoordinator) -> str:
    plan = c.data
    if plan is None or not plan.slots:
        return "–"
    return format_ranges(merge_ranges(plan.slots))


def _plan_attrs(c: SimpleChargeCoordinator) -> dict[str, Any]:
    plan = c.data
    if plan is None:
        return {}
    waiting = plan.waiting_for
    return {
        "slots": slot_list(plan.slots),
        "planned_hours": round(plan.planned_duration.total_seconds() / 3600, 2),
        "average_price": _round(plan.average_price, 3),
        "price_limit": _round(plan.threshold, 3),
        "waiting_for_forecast": format_ranges(merge_ranges(waiting)) if waiting else None,
        "forecast_slots": slot_list(waiting),
        "forecast_average_price": _round(average(waiting), 3),
        "force_window": format_ranges([plan.active_force_window]) if plan.active_force_window else None,
        "known_prices_until": c.prices[-1].end.isoformat() if c.prices else None,
        "forecast_until": c.forecast[-1].end.isoformat() if c.forecast else None,
        "last_charge_end": c.last_charge_end.isoformat() if c.last_charge_end else None,
        "unit": c.unit,
    }


def _charger_attrs(c: SimpleChargeCoordinator) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "control_type": c.charger.control_type,
        "target_entity": c.charger.target_entity,
        "last_command": None if c.charger.wanted is None else ("on" if c.charger.wanted else "off"),
        "attempts": c.charger.attempts,
    }
    if c.garo is not None:
        attrs["garo_schedule_last_synced"] = c.garo.last_synced.isoformat() if c.garo.last_synced else None
        attrs["garo_schedule_error"] = c.garo.last_error
    return attrs


SENSORS: tuple[SimpleChargeSensorDescription, ...] = (
    SimpleChargeSensorDescription(
        key="plan",
        icon="mdi:calendar-clock",
        value_fn=_plan_value,
        attrs_fn=_plan_attrs,
    ),
    SimpleChargeSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[str(r) for r in Reason],
        value_fn=lambda c: str(c.data.reason) if c.data else None,
    ),
    SimpleChargeSensorDescription(
        key="next_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: c.data.next_start(dt_util.now()) if c.data else None,
    ),
    SimpleChargeSensorDescription(
        key="price_limit",
        icon="mdi:cash-lock",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        price_unit=True,
        value_fn=lambda c: _round(c.data.threshold, 4) if c.data else None,
    ),
    SimpleChargeSensorDescription(
        key="reference_price",
        icon="mdi:scale-balance",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        price_unit=True,
        value_fn=lambda c: _round(c.reference_price, 4),
    ),
    SimpleChargeSensorDescription(
        key="needed_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.duration.total_seconds() / 3600, 3),
    ),
    SimpleChargeSensorDescription(
        key="charger",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=[STATUS_IDLE, STATUS_OK, STATUS_PENDING, STATUS_UNAVAILABLE, STATUS_FAILED],
        value_fn=lambda c: c.charger.status,
        attrs_fn=_charger_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SimpleChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SimpleChargeSensor(coordinator, d) for d in SENSORS)


class SimpleChargeSensor(SimpleChargeEntity, SensorEntity):
    entity_description: SimpleChargeSensorDescription
    _unrecorded_attributes = frozenset({"slots", "forecast_slots"})

    def __init__(self, coordinator: SimpleChargeCoordinator, description: SimpleChargeSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.price_unit:
            return self.coordinator.unit
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)
