"""Base entity for Simple Charge."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN, NAME
from .coordinator import SimpleChargeCoordinator

VERSION_URL = "https://github.com/tengmo-ab/simple-charge"

# Entity ids stay English whatever language Home Assistant runs in, so docs and
# automations can rely on them (for example binary_sensor.simple_charge_charge_now).
OBJECT_IDS = {
    "charge_now": "charge_now",
    "plan": "plan",
    "status": "status",
    "next_start": "next_start",
    "price_limit": "price_limit",
    "reference_price": "reference_price",
    "needed_duration": "needed_charging_time",
    "charger": "charger_command",
    "mode": "mode",
    "deadline_mode": "ready_by_mode",
    "charger_control": "control_charger",
    "deadline_enabled": "ready_by",
    "use_forecast": "use_price_forecast",
    "garo_schedule_sync": "write_garo_schedule",
    "duration": "charging_time",
    "max_price": "max_price",
    "relative_limit": "relative_limit",
    "target_soc": "target_battery_level",
    "deadline": "ready_by_time",
    "force_window_start": "force_window_start",
    "force_window_end": "force_window_end",
}


class SimpleChargeEntity(CoordinatorEntity[SimpleChargeCoordinator]):
    """All Simple Charge entities hang off one service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SimpleChargeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        # Home Assistant prefixes this with the device name: simple_charge_<id>.
        self._object_id = OBJECT_IDS.get(key, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.options.get(CONF_NAME) or NAME,
            manufacturer="Simple Charge",
            model="Price planner",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=VERSION_URL,
        )

    @property
    def suggested_object_id(self) -> str | None:
        return self._object_id

    @property
    def settings(self) -> dict:
        return self.coordinator.settings
